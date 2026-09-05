from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import pandas as pd

from src.config import Config

logger = logging.getLogger(__name__)


def _row_hash(row: pd.Series) -> str:
    payload = "|".join(str(v) for v in row.to_numpy())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stamp(df: pd.DataFrame, sheet: str, run_id: str, ingested_at: str) -> pd.DataFrame:
    df = df.copy()
    df["_row_hash"] = df.apply(_row_hash, axis=1)
    df["_run_id"] = run_id
    df["_ingested_at"] = ingested_at
    df["_source_sheet"] = sheet
    return df


def ingest(config: Config, run_id: str) -> dict[str, pd.DataFrame]:
    if not config.paths.workbook.exists():
        raise FileNotFoundError(f"source workbook not found: {config.paths.workbook}")

    ingested_at = datetime.now(timezone.utc).isoformat()
    xl = pd.ExcelFile(config.paths.workbook)
    missing = [s for s in config.sheets if s not in xl.sheet_names]
    if missing:
        raise ValueError(f"workbook is missing required sheet(s): {missing}")

    config.paths.bronze.mkdir(parents=True, exist_ok=True)
    tables: dict[str, pd.DataFrame] = {}
    for sheet in config.sheets:
        df = pd.read_excel(xl, sheet)
        if sheet == "flights":
            # duration mixes datetime.time and one datetime.datetime (Excel's
            # negative-time artefact on SJ192) in the same object column -
            # parquet cannot serialize a mixed-type column, so nulls are kept
            # as nulls and everything else is stored as its string repr.
            # clean.py recomputes duration from the timestamps and uses this
            # only as a reconciliation source.
            df["duration"] = df["duration"].map(lambda v: v if pd.isna(v) else str(v))
        if sheet == "payments":
            # amount mixes float, int and the literal string "INVALID" - same
            # mixed-type problem, same fix. clean.py classifies each value's
            # amount_quality from this raw string.
            df["amount"] = df["amount"].map(lambda v: v if pd.isna(v) else str(v))
        stamped = _stamp(df, sheet, run_id, ingested_at)
        out_path = config.paths.bronze / f"{sheet}.parquet"
        stamped.to_parquet(out_path, index=False)
        logger.info("ingested %s: %d rows -> %s", sheet, len(stamped), out_path)
        tables[sheet] = stamped
    return tables
