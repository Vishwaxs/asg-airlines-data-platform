from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import pandas as pd

from src.clean import CleanResult, clean, write_silver
from src.config import Config, load_config
from src.ingest import ingest
from src.kpi import (
    build_anomaly_summary,
    build_dq_scores,
    export_gold,
    load_extras_into_warehouse,
    read_views,
    write_dq_report,
)
from src.logging_setup import setup_logging
from src.model import build_model, load_duckdb
from src.validate import validate, write_summary

logger = logging.getLogger(__name__)

SILVER_TABLES = ["flights", "bookings", "payments", "passengers"]


@dataclass
class StageMetric:
    name: str
    started_at: str
    ended_at: str
    duration_seconds: float
    rows_in: int
    rows_out: int
    rows_quarantined: int
    status: str


@dataclass
class RunContext:
    run_id: str
    config: Config
    bronze: dict[str, pd.DataFrame] = field(default_factory=dict)
    validated: dict[str, pd.DataFrame] = field(default_factory=dict)
    rule_results: list = field(default_factory=list)
    clean_result: CleanResult | None = None
    model: dict[str, pd.DataFrame] = field(default_factory=dict)
    views: dict[str, pd.DataFrame] = field(default_factory=dict)
    extras: dict[str, pd.DataFrame] = field(default_factory=dict)
    ingested_counts: dict[str, int] = field(default_factory=dict)
    metrics: list[StageMetric] = field(default_factory=list)


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def _rows(tables: dict[str, pd.DataFrame]) -> int:
    return sum(len(df) for df in tables.values())


def _ensure_bronze(ctx: RunContext) -> None:
    if ctx.bronze:
        return
    paths = {name: ctx.config.paths.bronze / f"{name}.parquet" for name in ctx.config.sheets}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"bronze layer missing, run the ingest stage first: {missing}")
    ctx.bronze = {name: pd.read_parquet(path) for name, path in paths.items()}
    ctx.ingested_counts = {name: len(df) for name, df in ctx.bronze.items()}


def _ensure_validated(ctx: RunContext) -> None:
    if ctx.validated:
        return
    _ensure_bronze(ctx)
    ctx.validated, ctx.rule_results = validate(ctx.bronze)


def _ensure_clean(ctx: RunContext) -> None:
    if ctx.clean_result is not None:
        return
    _ensure_validated(ctx)
    ctx.clean_result = clean(ctx.validated, ctx.config)


def _ensure_model(ctx: RunContext) -> None:
    if ctx.model:
        return
    _ensure_clean(ctx)
    ctx.model = build_model(ctx.clean_result.silver, ctx.config)


def stage_ingest(ctx: RunContext) -> StageMetric:
    ctx.bronze = ingest(ctx.config, ctx.run_id)
    ctx.ingested_counts = {name: len(df) for name, df in ctx.bronze.items()}
    rows = _rows(ctx.bronze)
    return StageMetric("ingest", "", "", 0.0, rows, rows, 0, "ok")


def stage_validate(ctx: RunContext) -> StageMetric:
    _ensure_bronze(ctx)
    ctx.validated, ctx.rule_results = validate(ctx.bronze)
    write_summary(ctx.rule_results, ctx.config.paths.reports / "validation_summary.md")

    errors = sum(r.failed for r in ctx.rule_results if r.severity == "error")
    warnings = sum(r.failed for r in ctx.rule_results if r.severity == "warning")
    logger.info("validation: %d error-severity and %d warning-severity failures", errors, warnings)
    rows = _rows(ctx.validated)
    return StageMetric("validate", "", "", 0.0, rows, rows, 0, "ok")


def stage_clean(ctx: RunContext) -> StageMetric:
    _ensure_validated(ctx)
    rows_in = _rows(ctx.validated)
    ctx.clean_result = clean(ctx.validated, ctx.config)
    write_silver(ctx.clean_result, ctx.config)

    quarantined = sum(len(df) for df in ctx.clean_result.quarantine.values())
    return StageMetric(
        "clean", "", "", 0.0, rows_in, _rows(ctx.clean_result.silver), quarantined, "ok"
    )


def stage_model(ctx: RunContext) -> StageMetric:
    _ensure_clean(ctx)
    rows_in = _rows(ctx.clean_result.silver)
    ctx.model = build_model(ctx.clean_result.silver, ctx.config)
    load_duckdb(ctx.model, ctx.config)
    return StageMetric("model", "", "", 0.0, rows_in, _rows(ctx.model), 0, "ok")


def stage_kpi(ctx: RunContext) -> StageMetric:
    _ensure_model(ctx)
    anomalies = build_anomaly_summary(ctx.clean_result, ctx.ingested_counts)
    dq = build_dq_scores(ctx.clean_result, ctx.ingested_counts)
    ctx.extras = {"anomaly_summary": anomalies, "dq_score": dq}
    if not ctx.clean_result.survivorship.empty:
        ctx.extras["passenger_survivorship"] = ctx.clean_result.survivorship

    load_extras_into_warehouse(ctx.extras, ctx.config)
    ctx.views = read_views(ctx.config)
    rows = _rows(ctx.views)
    logger.info("computed %d kpi views, %d anomaly types", len(ctx.views), len(anomalies))
    return StageMetric("kpi", "", "", 0.0, _rows(ctx.model), rows, 0, "ok")


def stage_export(ctx: RunContext) -> StageMetric:
    if not ctx.views:
        stage_kpi(ctx)
    written = export_gold(ctx.model, ctx.views, ctx.extras, ctx.config)
    write_dq_report(
        ctx.clean_result, ctx.extras["anomaly_summary"], ctx.extras["dq_score"], ctx.views,
        ctx.ingested_counts, ctx.config,
    )
    return StageMetric("export", "", "", 0.0, len(written), len(written), 0, "ok")


STAGES = {
    "ingest": stage_ingest,
    "validate": stage_validate,
    "clean": stage_clean,
    "model": stage_model,
    "kpi": stage_kpi,
    "export": stage_export,
}


def run_stage(ctx: RunContext, name: str) -> StageMetric:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("stage %s starting", name)
    try:
        metric = STAGES[name](ctx)
    except Exception:
        elapsed = time.perf_counter() - started
        ctx.metrics.append(
            StageMetric(
                name, started_at, datetime.now(timezone.utc).isoformat(), round(elapsed, 3),
                0, 0, 0, "failed",
            )
        )
        raise

    elapsed = time.perf_counter() - started
    metric.started_at = started_at
    metric.ended_at = datetime.now(timezone.utc).isoformat()
    metric.duration_seconds = round(elapsed, 3)
    ctx.metrics.append(metric)
    logger.info(
        "stage %s done in %.2fs: %d rows in, %d rows out, %d quarantined",
        name, elapsed, metric.rows_in, metric.rows_out, metric.rows_quarantined,
    )
    return metric


def write_manifest(ctx: RunContext, log_path, status: str) -> dict:
    headline = ctx.views["v_kpi_headline"].iloc[0].to_dict() if ctx.views else {}
    manifest = {
        "run_id": ctx.run_id,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_workbook": str(ctx.config.paths.workbook.name),
        "log": str(log_path.name),
        "stages": [asdict(m) for m in ctx.metrics],
        "rows_ingested": ctx.ingested_counts,
        "rows_modelled": {name: len(df) for name, df in ctx.model.items()},
        "quarantined": {
            name: len(df) for name, df in (ctx.clean_result.quarantine.items()
                                           if ctx.clean_result else [])
        },
        "anomalies": ctx.clean_result.anomalies if ctx.clean_result else {},
        "duration_reconciliation": ctx.clean_result.reconciliation if ctx.clean_result else {},
        "headline": {k: (None if pd.isna(v) else v) for k, v in headline.items()},
    }
    path = ctx.config.paths.reports / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", path)
    return manifest


def print_plan(config: Config) -> None:
    print(f"workbook: {config.paths.workbook} (exists: {config.paths.workbook.exists()})")
    print(f"warehouse: {config.paths.warehouse}")
    print(f"date dimension: {config.date_start} to {config.date_end}")
    print("stages:")
    for i, name in enumerate(STAGES, start=1):
        print(f"  {i}. {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.pipeline")
    parser.add_argument("--stage", choices=list(STAGES), help="run a single stage")
    parser.add_argument("--dry-run", action="store_true", help="validate config and print the plan")
    args = parser.parse_args(argv)

    config = load_config()
    if args.dry_run:
        print_plan(config)
        return 0

    run_id = new_run_id()
    log_path = setup_logging(run_id, config.paths.logs)
    ctx = RunContext(run_id=run_id, config=config)
    logger.info("run %s starting", run_id)

    stages = [args.stage] if args.stage else list(STAGES)
    try:
        for name in stages:
            run_stage(ctx, name)
    except Exception as exc:
        logger.error("run %s failed in stage %s: %s", run_id, ctx.metrics[-1].name, exc)
        write_manifest(ctx, log_path, "failed")
        raise

    manifest = write_manifest(ctx, log_path, "ok")
    _print_summary(ctx, manifest)
    return 0


def _print_summary(ctx: RunContext, manifest: dict) -> None:
    print()
    print(f"run {ctx.run_id}")
    for stage in manifest["stages"]:
        print(
            f"  {stage['name']:<9} {stage['duration_seconds']:>6.2f}s  "
            f"in {stage['rows_in']:>5}  out {stage['rows_out']:>5}  "
            f"quarantined {stage['rows_quarantined']}"
        )
    if ctx.views:
        headline = ctx.views["v_kpi_headline"].iloc[0]
        print()
        print(f"  flights {int(headline['flights'])}, bookings {int(headline['bookings'])}, "
              f"passengers {int(headline['passengers'])}")
        print(f"  gross revenue {headline['gross_revenue']:,.2f}, "
              f"confirmed revenue {headline['confirmed_revenue']:,.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
