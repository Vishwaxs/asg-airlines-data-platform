from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

from src.config import Config
from src.pii import mask_email, mask_name, mask_phone, passenger_surrogate_key

logger = logging.getLogger(__name__)

REAL_AIRLINES = {"IndiGo", "SpiceJet", "Air India", "Vistara"}
VALID_STATUSES = {"CONFIRMED", "CANCELLED", "PENDING"}
# Matches both "02:54:00" and the Excel negative-time artefact
# "1899-12-29 05:00:00", and tolerates the fractional seconds that 27 rows carry.
DURATION_TAIL = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$")


@dataclass
class CleanResult:
    silver: dict[str, pd.DataFrame]
    quarantine: dict[str, pd.DataFrame]
    anomalies: dict[str, int] = field(default_factory=dict)
    survivorship: pd.DataFrame = field(default_factory=pd.DataFrame)
    reconciliation: dict[str, float] = field(default_factory=dict)


def business_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not c.startswith("_")]


def parse_source_duration(value: object) -> float | None:
    """Minutes from the raw duration cell, whether it is a time or Excel's negative-time datetime."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    match = DURATION_TAIL.search(text)
    if not match:
        return None
    hours, minutes, seconds = (int(g) for g in match.groups()[:3])
    fraction = float(f"0.{match.group(4)}") if match.group(4) else 0.0
    return round(hours * 60 + minutes + (seconds + fraction) / 60, 4)


def clean_flights(df: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    flights = df.copy()
    anomalies: dict[str, int] = {}

    flights["departure_ts"] = pd.to_datetime(flights["departure_time"])
    flights["arrival_ts"] = pd.to_datetime(flights["arrival_time"])
    flights["source_duration_minutes"] = flights["duration"].map(parse_source_duration)

    raw_minutes = (flights["arrival_ts"] - flights["departure_ts"]).dt.total_seconds() / 60
    flights["raw_duration_minutes"] = raw_minutes

    # The only defensible reading of a negative duration here is a date that
    # failed to roll over at midnight; the raw duration column agrees with the
    # rolled-forward value, which is what makes this a reconciliation rather
    # than a guess.
    negative = raw_minutes < 0
    anomalies["negative_duration"] = int(negative.sum())
    flights.loc[negative, "arrival_ts"] = flights.loc[negative, "arrival_ts"] + pd.Timedelta(days=1)
    flights["was_corrected"] = negative
    flights["correction_reason"] = pd.Series(
        ["arrival_rolled_forward_one_day" if n else None for n in negative], index=flights.index
    )

    flights["duration_minutes"] = (
        (flights["arrival_ts"] - flights["departure_ts"]).dt.total_seconds() / 60
    ).round(2)

    uncorrectable = (flights["duration_minutes"] < 0) | (
        flights["duration_minutes"] > config.max_duration_hours * 60
    )
    anomalies["uncorrectable_duration"] = int(uncorrectable.sum())

    # Reconciliation against the source column: pre-correction, exactly the
    # rows we rolled forward should disagree, each by exactly one day.
    delta_before = flights["raw_duration_minutes"] - flights["source_duration_minutes"]
    delta_after = flights["duration_minutes"] - flights["source_duration_minutes"]
    reconciliation = {
        "source_parseable": int(flights["source_duration_minutes"].notna().sum()),
        "mismatch_before_correction": int((delta_before.abs() > 0.5).sum()),
        "mismatch_after_correction": int((delta_after.abs() > 0.5).sum()),
        "max_abs_delta_before": float(delta_before.abs().max()),
        "max_abs_delta_after": float(delta_after.abs().max()),
    }
    flights["duration_reconciliation_delta"] = delta_after

    flights["is_overnight"] = flights["departure_ts"].dt.date != flights["arrival_ts"].dt.date
    flights["departure_hour"] = flights["departure_ts"].dt.hour
    flights["is_red_eye"] = (flights["departure_hour"] >= config.red_eye_start_hour) | (
        flights["departure_hour"] <= config.red_eye_end_hour
    )

    flights["airline_clean"] = flights["airline"].where(
        flights["airline"].isin(REAL_AIRLINES), "UNKNOWN"
    )
    flights["airline_is_unknown"] = flights["airline_clean"].eq("UNKNOWN")
    anomalies["missing_airline"] = int(flights["airline"].isna().sum())
    anomalies["sentinel_airline"] = int((flights["airline"] == "UNKNOWN").sum())

    # Duplicate keys split two ways: byte-identical rows are a harmless
    # re-emission and collapse to one; rows that disagree on a business column
    # cannot be arbitrated, so the whole group leaves rather than one of them
    # being silently picked.
    dup_ids = flights.loc[flights["flight_id"].duplicated(keep=False), "flight_id"].unique()
    hash_per_id = flights.groupby("flight_id")["_row_hash"].nunique()
    exact_dup_ids = [fid for fid in dup_ids if hash_per_id[fid] == 1]
    conflicting_ids = [fid for fid in dup_ids if hash_per_id[fid] > 1]

    conflicting = flights["flight_id"].isin(conflicting_ids)
    quarantine = flights[conflicting | uncorrectable].copy()
    quarantine["quarantine_reason"] = None
    quarantine.loc[conflicting[conflicting].index, "quarantine_reason"] = "conflicting_duplicate_key"
    quarantine.loc[uncorrectable[uncorrectable].index, "quarantine_reason"] = (
        "uncorrectable_duration"
    )

    kept = flights[~(conflicting | uncorrectable)].copy()
    before_collapse = len(kept)
    kept = kept.drop_duplicates(subset=["flight_id", "_row_hash"], keep="first")
    anomalies["exact_duplicate"] = before_collapse - len(kept)
    anomalies["conflicting_duplicate_key"] = int(conflicting.sum())

    logger.info(
        "flights: %d exact duplicate rows collapsed, %d rows quarantined (%s)",
        anomalies["exact_duplicate"], len(quarantine), ", ".join(conflicting_ids) or "none",
    )

    silver = kept[
        [
            "flight_id", "airline", "airline_clean", "airline_is_unknown", "source", "destination",
            "departure_ts", "arrival_ts", "duration_minutes", "source_duration_minutes",
            "duration_reconciliation_delta", "was_corrected", "correction_reason", "is_overnight",
            "is_red_eye", "departure_hour", "_run_id",
        ]
    ].copy()
    silver["route_label"] = silver["source"] + "-" + silver["destination"]

    quarantine_out = quarantine[
        ["flight_id", "airline", "source", "destination", "departure_ts", "arrival_ts",
         "duration_minutes", "quarantine_reason", "_run_id"]
    ].copy()

    return silver, quarantine_out, anomalies, reconciliation


def clean_bookings(df: pd.DataFrame, quarantined_flight_ids: set[str]) -> tuple[pd.DataFrame, dict]:
    bookings = df.copy()
    anomalies = {
        "missing_status": int(bookings["status"].isna().sum()),
        "sentinel_status": int((bookings["status"] == "INVALID").sum()),
    }

    status = bookings["status"]
    bookings["status_clean"] = status.where(status.isin(VALID_STATUSES | {"INVALID"}), "UNKNOWN")
    bookings["status_clean"] = bookings["status_clean"].fillna("UNKNOWN")
    bookings["status_is_valid"] = bookings["status_clean"].isin(VALID_STATUSES)
    bookings["booking_date"] = pd.to_datetime(bookings["booking_date"])
    bookings["references_quarantined_flight"] = bookings["flight_id"].isin(quarantined_flight_ids)
    anomalies["booking_on_quarantined_flight"] = int(
        bookings["references_quarantined_flight"].sum()
    )

    # passport_number and emergency_contact_* are dropped rather than masked:
    # no KPI needs them, and the cheapest control for data you do not need is
    # not to carry it past bronze.
    silver = bookings[
        ["booking_id", "passenger_id", "flight_id", "booking_date", "status", "status_clean",
         "status_is_valid", "seat_number", "references_quarantined_flight", "_run_id"]
    ].copy()
    return silver, anomalies


def clean_payments(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    payments = df.copy()
    raw = payments["amount"]
    numeric = pd.to_numeric(raw, errors="coerce")

    # A null and the literal string "INVALID" are two different upstream
    # failures; to_numeric(errors="coerce") would collapse them into one.
    quality = pd.Series("valid", index=payments.index)
    quality[raw.isna()] = "missing"
    quality[raw.notna() & numeric.isna()] = "non_numeric"
    payments["amount"] = numeric
    payments["amount_quality"] = quality

    anomalies = {
        "missing_amount": int((quality == "missing").sum()),
        "non_numeric_amount": int((quality == "non_numeric").sum()),
    }
    silver = payments[
        ["payment_id", "booking_id", "amount", "amount_quality", "payment_method", "_run_id"]
    ].copy()
    return silver, anomalies


def _survivor_reason(group: pd.DataFrame, null_counts: pd.Series) -> tuple[int, str]:
    fewest = null_counts[group.index].min()
    candidates = group.index[null_counts[group.index] == fewest]
    if len(candidates) == 1:
        return candidates[0], "fewest_nulls"

    full_length = group.loc[candidates, "aadhaar_id"].astype(str).str.len() == 12
    if full_length.any():
        narrowed = candidates[full_length.to_numpy()]
        if len(narrowed) == 1:
            return narrowed[0], "aadhaar_full_length"
        candidates = narrowed

    email_order = group.loc[candidates, "email"].astype(str).sort_values()
    return email_order.index[0], "lowest_email"


def clean_passengers(
    df: pd.DataFrame, config: Config, pepper: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    passengers = df.copy()
    cols = business_columns(passengers)
    null_counts = passengers[cols].isna().sum(axis=1)

    aadhaar_str = passengers["aadhaar_id"].astype(str)
    anomalies = {
        "missing_last_name": int(passengers["last_name"].isna().sum()),
        "aadhaar_length_anomaly": int((aadhaar_str.str.len() != 12).sum()),
        "duplicate_passenger_id": int(passengers["passenger_id"].duplicated(keep=False).sum()),
    }

    survivor_rows: list[int] = []
    survivorship_log: list[dict] = []
    for pid, group in passengers.groupby("passenger_id"):
        if len(group) == 1:
            survivor_rows.append(group.index[0])
            continue
        winner, reason = _survivor_reason(group, null_counts)
        survivor_rows.append(winner)
        for idx in group.index:
            survivorship_log.append(
                {
                    "passenger_id": pid,
                    "candidate_row": int(idx),
                    "null_count": int(null_counts[idx]),
                    "aadhaar_digits": len(aadhaar_str[idx]),
                    "email_masked": mask_email(str(passengers.loc[idx, "email"])),
                    "survived": idx == winner,
                    "reason": reason if idx == winner else "",
                }
            )

    survivors = passengers.loc[sorted(survivor_rows)].copy()
    logger.info(
        "passengers: %d rows collapsed to %d by survivorship", len(passengers), len(survivors)
    )

    survivors["passenger_sk"] = [
        passenger_surrogate_key(v, pepper, config.token_hex_length)
        for v in survivors["aadhaar_id"]
    ]
    survivors["masked_name"] = [
        mask_name(f, l) for f, l in zip(survivors["first_name"], survivors["last_name"])
    ]
    survivors["masked_email"] = survivors["email"].astype(str).map(mask_email)
    survivors["masked_phone"] = survivors["phone"].astype(str).map(mask_phone)
    survivors["age_band"] = survivors["age"].map(config.age_band)
    survivors["is_minor"] = survivors["age"] < 18
    survivors["aadhaar_digits"] = survivors["aadhaar_id"].astype(str).str.len()

    # date_of_birth leaves here: age alone is not identifying, DOB plus a name is.
    silver = survivors[
        ["passenger_sk", "passenger_id", "age", "age_band", "gender", "masked_name", "masked_email",
         "masked_phone", "is_minor", "aadhaar_digits", "_run_id"]
    ].copy()

    return silver, pd.DataFrame(survivorship_log), anomalies


def clean(tables: dict[str, pd.DataFrame], config: Config) -> CleanResult:
    pepper = config.pepper()

    flights, flights_q, flight_anomalies, reconciliation = clean_flights(tables["flights"], config)
    quarantined_ids = set(flights_q["flight_id"])
    bookings, booking_anomalies = clean_bookings(tables["bookings"], quarantined_ids)
    payments, payment_anomalies = clean_payments(tables["payments"])
    passengers, survivorship, passenger_anomalies = clean_passengers(
        tables["passengers"], config, pepper
    )

    anomalies = {
        **flight_anomalies, **booking_anomalies, **payment_anomalies, **passenger_anomalies
    }
    anomalies["booking_without_payment"] = int(
        (~bookings["booking_id"].isin(payments["booking_id"])).sum()
    )
    anomalies["flight_without_booking"] = int(
        (~flights["flight_id"].isin(bookings["flight_id"])).sum()
    )

    return CleanResult(
        silver={
            "flights": flights,
            "bookings": bookings,
            "payments": payments,
            "passengers": passengers,
        },
        quarantine={"flights": flights_q},
        anomalies=anomalies,
        survivorship=survivorship,
        reconciliation=reconciliation,
    )


def write_silver(result: CleanResult, config: Config) -> None:
    config.paths.silver.mkdir(parents=True, exist_ok=True)
    config.paths.quarantine.mkdir(parents=True, exist_ok=True)
    for name, df in result.silver.items():
        df.to_parquet(config.paths.silver / f"{name}.parquet", index=False)
    for name, df in result.quarantine.items():
        df.to_csv(config.paths.quarantine / f"{name}.csv", index=False)
    if not result.survivorship.empty:
        result.survivorship.to_csv(
            config.paths.reports / "passenger_survivorship.csv", index=False
        )
