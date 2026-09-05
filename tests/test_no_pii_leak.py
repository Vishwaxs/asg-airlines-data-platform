"""Scans every committed artefact for raw PII. This is the control that has to hold."""

import re

import pandas as pd
import pytest

from src.config import load_config

PHONE = re.compile(r"^\+91-\d{10}$")
PASSPORT = re.compile(r"^[A-Z]\d{7}$")
AADHAAR_SHAPED = re.compile(r"^\d{10,12}$")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}")
DOB = re.compile(r"^\d{4}-\d{2}-\d{2}")

FORBIDDEN_COLUMNS = {
    "first_name", "last_name", "email", "phone", "aadhaar_id", "date_of_birth",
    "passport_number", "emergency_contact_name", "emergency_contact_phone",
}
MASKED_COLUMNS = {"masked_email", "masked_phone", "masked_name", "email_masked"}


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def gold_files(config):
    files = sorted(config.paths.gold.glob("*.csv"))
    if not files:
        pytest.skip("no gold layer on disk; run python -m src.pipeline first")
    return files


def _cells(df: pd.DataFrame, column: str) -> list[str]:
    return [str(v) for v in df[column].dropna().unique()]


def test_gold_carries_no_raw_pii_columns(gold_files):
    for path in gold_files:
        columns = set(pd.read_csv(path, nrows=1).columns)
        leaked = columns & FORBIDDEN_COLUMNS
        assert not leaked, f"{path.name} exposes raw PII columns: {leaked}"


def test_gold_values_match_no_pii_pattern(gold_files):
    for path in gold_files:
        df = pd.read_csv(path, dtype=str)
        for column in df.columns:
            values = _cells(df, column)
            if not values:
                continue

            assert not any(PHONE.match(v) for v in values), f"{path.name}.{column} holds a raw phone"
            assert not any(PASSPORT.match(v) for v in values), (
                f"{path.name}.{column} holds a passport number"
            )
            if column in MASKED_COLUMNS:
                continue
            assert not any("@" in v for v in values), (
                f"{path.name}.{column} holds an unmasked email"
            )


def test_no_aadhaar_shaped_identifier_survives(gold_files):
    for path in gold_files:
        df = pd.read_csv(path, dtype=str)
        for column in df.columns:
            if column in {"date_key", "booking_date_key", "departure_date_key"}:
                continue  # YYYYMMDD keys are 8 digits and not identifying
            values = _cells(df, column)
            offenders = [v for v in values if AADHAAR_SHAPED.match(v)]
            assert not offenders, f"{path.name}.{column} holds Aadhaar-shaped values: {offenders[:3]}"


def test_date_of_birth_does_not_survive_to_gold(gold_files):
    for path in gold_files:
        df = pd.read_csv(path, dtype=str)
        assert "date_of_birth" not in df.columns
        for column in df.columns:
            if "birth" in column.lower() or "dob" in column.lower():
                pytest.fail(f"{path.name}.{column} looks like a date of birth")


def test_masked_columns_are_actually_masked(config, gold_files):
    passengers = pd.read_csv(config.paths.gold / "dim_passenger.csv", dtype=str)
    assert passengers["masked_email"].str.contains(r"\*\*\*").all()
    assert passengers["masked_phone"].str.startswith("+91-XXXXXX").all()
    # A masked name keeps at most a surname initial.
    assert not passengers["masked_name"].str.contains(r"\s\w{2,}$").any()


def test_quarantine_files_are_pii_free(config):
    for path in sorted(config.paths.quarantine.glob("*.csv")):
        columns = set(pd.read_csv(path, nrows=1).columns)
        assert not columns & FORBIDDEN_COLUMNS, f"{path.name} exposes raw PII"


def test_survivorship_log_masks_the_emails_it_reports(config):
    path = config.paths.reports / "passenger_survivorship.csv"
    if not path.exists():
        pytest.skip("survivorship log not generated yet")
    log = pd.read_csv(path, dtype=str)
    assert "email" not in log.columns
    assert log["email_masked"].str.contains(r"\*\*\*").all()
