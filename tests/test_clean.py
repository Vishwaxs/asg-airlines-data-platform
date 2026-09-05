import pandas as pd
import pytest

from src.clean import clean, clean_flights, parse_source_duration
from src.config import load_config
from src.ingest import ingest
from src.validate import validate


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def cleaned(config):
    tables = ingest(config, run_id="pytest")
    flagged, _ = validate(tables)
    return clean(flagged, config)


def _synthetic(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["_row_hash"] = [f"hash{i}" for i in range(len(df))]
    df["_run_id"] = "pytest"
    return df


def test_sj192_corrects_to_exactly_300_minutes(cleaned):
    sj192 = cleaned.silver["flights"].query("flight_id == 'SJ192'").iloc[0]
    assert sj192["duration_minutes"] == 300.0
    assert sj192["was_corrected"]
    assert sj192["correction_reason"] == "arrival_rolled_forward_one_day"
    # The raw duration column is an independent witness to the corrected value.
    assert sj192["source_duration_minutes"] == 300.0


def test_reconciliation_finds_exactly_one_pre_correction_mismatch(cleaned):
    assert cleaned.reconciliation["source_parseable"] == 1020
    assert cleaned.reconciliation["mismatch_before_correction"] == 1
    assert cleaned.reconciliation["max_abs_delta_before"] == 1440.0
    assert cleaned.reconciliation["mismatch_after_correction"] == 0


def test_overnight_flight_keeps_its_duration(config):
    flights = _synthetic(
        [
            {
                "flight_id": "XX001", "airline": "IndiGo", "source": "DEL", "destination": "BOM",
                "departure_time": pd.Timestamp("2026-04-17 23:30:00"),
                "arrival_time": pd.Timestamp("2026-04-18 01:15:00"),
                "duration": "01:45:00",
            }
        ]
    )
    silver, quarantine, _, _ = clean_flights(flights, config)
    row = silver.iloc[0]
    assert row["duration_minutes"] == 105.0
    assert row["is_overnight"]
    assert row["is_red_eye"]
    assert not row["was_corrected"]
    assert quarantine.empty


def test_duration_beyond_a_day_is_quarantined_not_corrected(config):
    flights = _synthetic(
        [
            {
                "flight_id": "XX002", "airline": "Vistara", "source": "DEL", "destination": "MAA",
                "departure_time": pd.Timestamp("2026-04-17 06:00:00"),
                "arrival_time": pd.Timestamp("2026-04-19 06:00:00"),
                "duration": "48:00:00",
            }
        ]
    )
    silver, quarantine, _, _ = clean_flights(flights, config)
    assert silver.empty
    assert quarantine.iloc[0]["quarantine_reason"] == "uncorrectable_duration"


def test_exact_duplicates_collapse_conflicting_key_leaves(cleaned):
    flights = cleaned.silver["flights"]
    quarantine = cleaned.quarantine["flights"]

    assert cleaned.anomalies["exact_duplicate"] == 15
    assert set(quarantine["flight_id"]) == {"6F250"}
    assert len(quarantine) == 2
    # 1020 source rows = 1003 kept + 15 collapsed duplicates + 2 quarantined.
    assert len(flights) + cleaned.anomalies["exact_duplicate"] + len(quarantine) == 1020
    assert flights["flight_id"].is_unique
    # 1004 distinct ids survive dedup; 6F250 then leaves as a conflicting key.
    assert flights["flight_id"].nunique() == 1003
    assert "6F250" not in set(flights["flight_id"])


def test_bookings_on_a_quarantined_flight_are_kept(cleaned):
    bookings = cleaned.silver["bookings"]
    assert len(bookings) == 1000
    assert bookings["references_quarantined_flight"].sum() == 2


def test_payment_amount_quality_separates_null_from_sentinel(cleaned):
    payments = cleaned.silver["payments"]
    counts = payments["amount_quality"].value_counts()
    assert counts["missing"] == 48
    assert counts["non_numeric"] == 30
    assert counts["valid"] == 922
    assert payments["amount"].sum() == pytest.approx(7385142.98, abs=0.01)
    # Rows stay; only the value goes.
    assert len(payments) == 1000
    assert payments.loc[payments["amount_quality"] != "valid", "amount"].isna().all()


def test_status_null_and_sentinel_are_counted_separately(cleaned):
    assert cleaned.anomalies["missing_status"] == 45
    assert cleaned.anomalies["sentinel_status"] == 30
    bookings = cleaned.silver["bookings"]
    assert (bookings["status_clean"] == "UNKNOWN").sum() == 45
    assert (bookings["status_clean"] == "INVALID").sum() == 30
    assert not bookings.loc[bookings["status_clean"].isin(["UNKNOWN", "INVALID"]), "status_is_valid"].any()


def test_airline_null_and_sentinel_map_together_but_count_apart(cleaned):
    assert cleaned.anomalies["missing_airline"] == 41
    assert cleaned.anomalies["sentinel_airline"] == 31
    flights = cleaned.silver["flights"]
    assert flights.loc[flights["airline_is_unknown"], "airline_clean"].eq("UNKNOWN").all()


def test_passenger_survivorship_is_deterministic_and_logged(cleaned):
    passengers = cleaned.silver["passengers"]
    assert len(passengers) == 1000
    assert passengers["passenger_id"].is_unique
    assert passengers["passenger_sk"].is_unique

    log = cleaned.survivorship
    assert len(log) == 75
    assert log["passenger_id"].nunique() == 36
    assert log["survived"].sum() == 36
    assert set(log.loc[log["survived"], "reason"]) <= {
        "fewest_nulls", "aadhaar_full_length", "lowest_email"
    }


def test_survivorship_repeats_exactly_on_a_second_run(config):
    tables = ingest(config, run_id="pytest-repeat")
    flagged, _ = validate(tables)
    first = clean(flagged, config).silver["passengers"]["passenger_sk"].tolist()
    second = clean(flagged, config).silver["passengers"]["passenger_sk"].tolist()
    assert first == second


def test_dropped_pii_columns_are_gone_from_silver(cleaned):
    passengers = cleaned.silver["passengers"].columns
    for column in ["first_name", "last_name", "email", "phone", "aadhaar_id", "date_of_birth"]:
        assert column not in passengers
    bookings = cleaned.silver["bookings"].columns
    for column in ["passport_number", "emergency_contact_name", "emergency_contact_phone"]:
        assert column not in bookings


def test_parse_source_duration_handles_every_shape_in_the_workbook():
    assert parse_source_duration("02:54:00") == 174.0
    assert parse_source_duration("1899-12-29 05:00:00") == 300.0
    assert parse_source_duration("02:00:00.298000") == pytest.approx(120.005, abs=0.001)
    assert parse_source_duration(None) is None
