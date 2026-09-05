from __future__ import annotations

import logging

import duckdb
import pandas as pd

from src.clean import CleanResult
from src.config import Config

logger = logging.getLogger(__name__)

# Which source table each anomaly is a rate against. Delay is deliberately
# absent: the workbook has no scheduled-vs-actual pair, so operational delay
# is not computable and is not invented here.
ANOMALY_SCOPE = {
    "negative_duration": "flights",
    "uncorrectable_duration": "flights",
    "conflicting_duplicate_key": "flights",
    "exact_duplicate": "flights",
    "missing_airline": "flights",
    "sentinel_airline": "flights",
    "flight_without_booking": "flights",
    "missing_status": "bookings",
    "sentinel_status": "bookings",
    "booking_without_payment": "bookings",
    "booking_on_quarantined_flight": "bookings",
    "missing_amount": "payments",
    "non_numeric_amount": "payments",
    "missing_last_name": "passengers",
    "duplicate_passenger_id": "passengers",
    "aadhaar_length_anomaly": "passengers",
}

KPI_VIEWS = [
    "v_kpi_headline",
    "v_flight_summary",
    "v_flights_by_airline",
    "v_route_performance",
    "v_route_revenue",
    "v_departure_hour_profile",
    "v_booking_status",
    "v_bookings_monthly",
    "v_revenue_summary",
    "v_payment_quality",
    "v_passenger_profile",
]


def build_anomaly_summary(result: CleanResult, ingested: dict[str, int]) -> pd.DataFrame:
    rows = []
    for anomaly, count in sorted(result.anomalies.items()):
        scope = ANOMALY_SCOPE.get(anomaly, "flights")
        denominator = ingested[scope]
        rows.append(
            {
                "anomaly": anomaly,
                "scope_table": scope,
                "count": count,
                "scope_rows": denominator,
                "rate_pct": round(100.0 * count / denominator, 3),
            }
        )
    return pd.DataFrame(rows)


def build_dq_scores(result: CleanResult, ingested: dict[str, int]) -> pd.DataFrame:
    """dq_score = 1 - (quarantined + flagged) / ingested, per source table."""
    silver = result.silver
    flights, bookings, payments, passengers = (
        silver["flights"], silver["bookings"], silver["payments"], silver["passengers"]
    )
    anomalies = result.anomalies

    flagged = {
        # A row counts once however many flags it carries.
        "flights": int((flights["airline_is_unknown"] | flights["was_corrected"]).sum()),
        "bookings": int((~bookings["status_is_valid"]).sum()),
        "payments": int((payments["amount_quality"] != "valid").sum()),
        "passengers": int((passengers["aadhaar_digits"] != 12).sum()),
    }
    quarantined = {
        "flights": sum(len(df) for df in result.quarantine.values()),
        "bookings": 0,
        "payments": 0,
        "passengers": 0,
    }
    collapsed = {
        "flights": anomalies["exact_duplicate"],
        "bookings": 0,
        "payments": 0,
        "passengers": ingested["passengers"] - len(passengers),
    }
    retained = {
        "flights": len(flights), "bookings": len(bookings),
        "payments": len(payments), "passengers": len(passengers),
    }

    rows = []
    for table in ["flights", "bookings", "payments", "passengers"]:
        total = ingested[table]
        score = 1 - (quarantined[table] + flagged[table]) / total
        rows.append(
            {
                "table": table,
                "ingested": total,
                "flagged": flagged[table],
                "quarantined": quarantined[table],
                "collapsed_duplicates": collapsed[table],
                "retained": retained[table],
                "dq_score": round(score, 4),
            }
        )
    return pd.DataFrame(rows)


def read_views(config: Config) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(config.paths.warehouse), read_only=True)
    try:
        return {view: con.execute(f"SELECT * FROM {view}").df() for view in KPI_VIEWS}
    finally:
        con.close()


def export_gold(
    model: dict[str, pd.DataFrame], views: dict[str, pd.DataFrame], extras: dict[str, pd.DataFrame],
    config: Config,
) -> list[str]:
    config.paths.gold.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in {**model, **views, **extras}.items():
        path = config.paths.gold / f"{name}.csv"
        df.to_csv(path, index=False)
        written.append(path.name)
    logger.info("exported %d gold csv files to %s", len(written), config.paths.gold)
    return written


def load_extras_into_warehouse(extras: dict[str, pd.DataFrame], config: Config) -> None:
    con = duckdb.connect(str(config.paths.warehouse))
    try:
        for name, df in extras.items():
            con.register("staged", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM staged")
            con.unregister("staged")
    finally:
        con.close()


def write_dq_report(
    result: CleanResult,
    anomalies: pd.DataFrame,
    dq: pd.DataFrame,
    views: dict[str, pd.DataFrame],
    ingested: dict[str, int],
    config: Config,
) -> None:
    headline = views["v_kpi_headline"].iloc[0]
    recon = result.reconciliation
    total_ingested = sum(ingested.values())
    total_anomalies = int(anomalies["count"].sum())

    lines = [
        "# Data quality report",
        "",
        f"Run covers {total_ingested:,} ingested rows across four source sheets.",
        "",
        "## Scores",
        "",
        "`dq_score = 1 - (quarantined + flagged) / ingested`",
        "",
        "A flagged row is one carrying a quality defect but still usable: a missing or sentinel",
        "airline, a corrected duration, an invalid status, an unusable amount, a truncated Aadhaar.",
        "Flagged rows are retained. Quarantined rows are removed from the facts because they are",
        "ambiguous rather than merely incomplete. Collapsed rows are byte-identical duplicates.",
        "",
        dq.to_markdown(index=False),
        "",
        "## Anomaly taxonomy",
        "",
        "There is no delay measure here. The workbook carries no scheduled-versus-actual timestamp",
        "pair, so on-time performance is not computable from it; `scheduled_departure` and",
        "`actual_departure` are the two columns that would be required. What is computable is an",
        "anomaly rate, defined per source table below.",
        "",
        anomalies.to_markdown(index=False),
        "",
        f"Total anomaly incidences: {total_anomalies:,} across {total_ingested:,} ingested rows "
        f"({100.0 * total_anomalies / total_ingested:.2f} per 100 rows). A single row can carry",
        "more than one anomaly, so this is an incidence rate, not a share of rows.",
        "",
        "## Duration reconciliation",
        "",
        "Recomputed duration (`arrival_ts - departure_ts`) is checked against the source `duration`",
        "column, which is treated as an independent witness rather than as the authoritative value.",
        "",
        f"- source values parseable: {recon['source_parseable']} of {ingested['flights']}",
        f"- mismatches before correction: {recon['mismatch_before_correction']} "
        f"(max absolute delta {recon['max_abs_delta_before']:.0f} minutes)",
        f"- mismatches after correction: {recon['mismatch_after_correction']} "
        f"(max absolute delta {recon['max_abs_delta_after']:.3f} minutes)",
        "",
        "The single pre-correction mismatch is SJ192, off by exactly 1,440 minutes - one day. The",
        "raw duration column reads 05:00:00 for that row and the rolled-forward arrival gives",
        "exactly 300 minutes, so two independent sources agree on the corrected value.",
        "",
        "## Headline figures",
        "",
        f"- flights modelled: {int(headline['flights']):,}",
        f"- bookings modelled: {int(headline['bookings']):,}",
        f"- passengers modelled: {int(headline['passengers']):,}",
        f"- average duration: {headline['avg_duration_minutes']:.2f} minutes "
        f"(sigma {headline['stddev_duration_minutes']:.2f})",
        f"- gross revenue: {headline['gross_revenue']:,.2f}",
        f"- confirmed revenue: {headline['confirmed_revenue']:,.2f}",
        f"- cancellation rate: {headline['cancellation_rate_pct']:.2f}%",
        f"- payment coverage: {headline['payment_coverage_pct']:.2f}%",
        "",
        "## Passenger survivorship",
        "",
        f"{len(result.survivorship)} candidate rows across "
        f"{result.survivorship['passenger_id'].nunique()} duplicated passenger ids were resolved to "
        "one surviving row each. Every candidate and the reason its winner was chosen is in",
        "`reports/passenger_survivorship.csv`. Selection order: fewest nulls, then a full 12-digit",
        "Aadhaar, then the lexicographically smallest email. No group was resolved by row order.",
        "",
        result.survivorship[result.survivorship["survived"]]["reason"]
        .value_counts()
        .rename_axis("reason")
        .reset_index(name="groups")
        .to_markdown(index=False),
        "",
    ]
    path = config.paths.reports / "data_quality_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("wrote %s", path)


def run_kpi(
    result: CleanResult, model: dict[str, pd.DataFrame], ingested: dict[str, int], config: Config
) -> dict[str, pd.DataFrame]:
    anomalies = build_anomaly_summary(result, ingested)
    dq = build_dq_scores(result, ingested)
    extras = {"anomaly_summary": anomalies, "dq_score": dq}
    if not result.survivorship.empty:
        extras["passenger_survivorship"] = result.survivorship

    load_extras_into_warehouse(extras, config)
    views = read_views(config)
    export_gold(model, views, extras, config)
    write_dq_report(result, anomalies, dq, views, ingested, config)
    return views
