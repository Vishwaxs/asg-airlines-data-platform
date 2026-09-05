import pandas as pd
import pytest

from src.clean import clean
from src.config import load_config
from src.ingest import ingest
from src.model import UNKNOWN_FLIGHT_SK, build_model
from src.validate import validate

TRUE_REVENUE = 7385142.98
NAIVE_REVENUE = 7593758.92


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def model(config):
    tables = ingest(config, run_id="pytest-model")
    flagged, _ = validate(tables)
    return build_model(clean(flagged, config).silver, config)


def test_fact_booking_keeps_every_booking(model):
    assert len(model["fact_booking"]) == 1000
    assert model["fact_booking"]["booking_id"].is_unique


def test_payment_total_matches_the_source_sum(model):
    assert model["fact_payment"]["amount"].sum() == pytest.approx(TRUE_REVENUE, abs=0.01)
    assert len(model["fact_payment"]) == 1000


def test_quarantined_flight_bookings_land_on_the_unknown_member(model):
    fact_booking = model["fact_booking"]
    fact_flight = model["fact_flight"]

    assert "6F250" not in set(fact_flight["flight_id"])
    orphaned = fact_booking[fact_booking["flight_sk"] == UNKNOWN_FLIGHT_SK]
    assert len(orphaned) == 2
    # The unknown member exists, so the join stays inner and nothing is lost.
    assert UNKNOWN_FLIGHT_SK in set(fact_flight["flight_sk"])


def test_flight_sk_is_unique_which_is_what_dedup_buys(model):
    fact_flight = model["fact_flight"]
    assert fact_flight["flight_sk"].is_unique
    real = fact_flight[fact_flight["flight_sk"] != UNKNOWN_FLIGHT_SK]
    assert real["flight_id"].is_unique
    assert len(real) == 1003


def test_every_fact_key_resolves(model):
    fact_flight, fact_booking, fact_payment = (
        model["fact_flight"], model["fact_booking"], model["fact_payment"]
    )
    assert fact_flight["airline_key"].isin(model["dim_airline"]["airline_key"]).all()
    assert fact_flight["route_key"].isin(model["dim_route"]["route_key"]).all()
    assert fact_booking["flight_sk"].isin(fact_flight["flight_sk"]).all()
    assert fact_booking["passenger_sk"].isin(model["dim_passenger"]["passenger_sk"]).all()
    assert fact_booking["status_key"].isin(model["dim_status"]["status_key"]).all()
    assert fact_booking["booking_date_key"].isin(model["dim_date"]["date_key"]).all()
    assert fact_payment["booking_sk"].isin(fact_booking["booking_sk"]).all()

    departures = fact_flight["departure_date_key"].dropna()
    assert departures.isin(model["dim_date"]["date_key"]).all()


def test_star_schema_does_not_reproduce_the_fan_out(model):
    # The naive analyst join: bookings out to flights and payments in one go.
    fact_booking, fact_flight, fact_payment = (
        model["fact_booking"], model["fact_flight"], model["fact_payment"]
    )
    naive = fact_booking.merge(fact_flight, on="flight_sk", how="left").merge(
        fact_payment, on="booking_sk", how="left"
    )
    assert len(naive) == 1363  # one row per payment, plus unpaid bookings

    # Revenue read at payment grain is unaffected by that fan-out.
    assert fact_payment["amount"].sum() == pytest.approx(TRUE_REVENUE, abs=0.01)
    assert naive["amount"].sum() == pytest.approx(TRUE_REVENUE, abs=0.01)


def test_source_level_fan_out_inflation_is_what_the_model_avoids(config):
    # Reproduced from the raw sheets so the 208,615.94 figure in the docs has
    # a test standing behind it.
    xl = pd.ExcelFile(config.paths.workbook)
    flights = pd.read_excel(xl, "flights")
    bookings = pd.read_excel(xl, "bookings")
    payments = pd.read_excel(xl, "payments")

    joined = bookings.merge(flights, on="flight_id", how="left").merge(
        payments, on="booking_id", how="left"
    )
    assert len(joined) == 1404
    naive_sum = pd.to_numeric(joined["amount"], errors="coerce").sum()
    true_sum = pd.to_numeric(payments["amount"], errors="coerce").sum()
    assert naive_sum == pytest.approx(NAIVE_REVENUE, abs=0.01)
    assert true_sum == pytest.approx(TRUE_REVENUE, abs=0.01)
    assert naive_sum - true_sum == pytest.approx(208615.94, abs=0.01)


def test_dim_date_spans_both_ranges(model):
    dim_date = model["dim_date"]
    assert dim_date["date_key"].is_unique
    assert dim_date["date_key"].min() == 20250401
    assert dim_date["date_key"].max() == 20260531


def test_dim_passenger_carries_no_raw_identifiers(model):
    dim = model["dim_passenger"]
    assert dim["passenger_sk"].str.startswith("PSG_").all()
    assert set(dim.columns) == {
        "passenger_sk", "passenger_id", "age", "age_band", "gender", "masked_name",
        "masked_email", "masked_phone", "is_minor",
    }
