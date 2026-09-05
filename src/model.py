from __future__ import annotations

import logging

import duckdb
import pandas as pd

from src.config import Config

logger = logging.getLogger(__name__)

UNKNOWN_FLIGHT_SK = -1
UNKNOWN_ROUTE_KEY = -1

DIMENSION_ORDER = ["dim_date", "dim_airline", "dim_route", "dim_status", "dim_passenger"]
FACT_ORDER = ["fact_flight", "fact_booking", "fact_payment"]


def build_dim_date(config: Config) -> pd.DataFrame:
    # Spans both ranges: bookings run Apr 2025 - Apr 2026, flights sit in four
    # days of Apr 2026. One conformed date dimension, two relationships.
    dates = pd.date_range(config.date_start, config.date_end, freq="D")
    return pd.DataFrame(
        {
            "date_key": dates.strftime("%Y%m%d").astype(int),
            "date": dates.date,
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.strftime("%B"),
            "day": dates.day,
            "day_name": dates.strftime("%A"),
            "week": dates.isocalendar().week.to_numpy(),
            "is_weekend": dates.dayofweek >= 5,
        }
    )


def build_dim_airline(flights: pd.DataFrame) -> pd.DataFrame:
    names = sorted(flights["airline_clean"].unique())
    return pd.DataFrame(
        {
            "airline_key": range(1, len(names) + 1),
            "airline_name": names,
            "is_unknown": [n == "UNKNOWN" for n in names],
        }
    )


def build_dim_route(flights: pd.DataFrame) -> pd.DataFrame:
    routes = (
        flights[["source", "destination", "route_label"]]
        .drop_duplicates()
        .sort_values("route_label")
        .reset_index(drop=True)
    )
    routes.insert(0, "route_key", range(1, len(routes) + 1))
    unknown = pd.DataFrame(
        [{"route_key": UNKNOWN_ROUTE_KEY, "source": "UNK", "destination": "UNK",
          "route_label": "UNKNOWN"}]
    )
    return pd.concat([unknown, routes], ignore_index=True)


def build_dim_status(bookings: pd.DataFrame) -> pd.DataFrame:
    statuses = sorted(bookings["status_clean"].unique())
    return pd.DataFrame(
        {
            "status_key": range(1, len(statuses) + 1),
            "status": statuses,
            "is_valid": [s in {"CONFIRMED", "CANCELLED", "PENDING"} for s in statuses],
        }
    )


def build_dim_passenger(passengers: pd.DataFrame) -> pd.DataFrame:
    return passengers[
        ["passenger_sk", "passenger_id", "age", "age_band", "gender", "masked_name",
         "masked_email", "masked_phone", "is_minor"]
    ].reset_index(drop=True)


def build_fact_flight(
    flights: pd.DataFrame, dim_airline: pd.DataFrame, dim_route: pd.DataFrame
) -> pd.DataFrame:
    airline_keys = dict(zip(dim_airline["airline_name"], dim_airline["airline_key"]))
    route_keys = dict(zip(dim_route["route_label"], dim_route["route_key"]))

    fact = flights.sort_values("flight_id").reset_index(drop=True).copy()
    fact.insert(0, "flight_sk", range(1, len(fact) + 1))
    fact["airline_key"] = fact["airline_clean"].map(airline_keys)
    fact["route_key"] = fact["route_label"].map(route_keys)
    fact["departure_date_key"] = fact["departure_ts"].dt.strftime("%Y%m%d").astype(int)

    columns = [
        "flight_sk", "flight_id", "airline_key", "route_key", "departure_date_key", "departure_ts",
        "arrival_ts", "duration_minutes", "is_overnight", "is_red_eye", "departure_hour",
        "was_corrected", "correction_reason",
    ]
    fact = fact[columns]

    # Unknown member: bookings whose flight was quarantined point here rather
    # than being dropped, so booking counts stay whole and the join stays inner.
    unknown = pd.DataFrame(
        [
            {
                "flight_sk": UNKNOWN_FLIGHT_SK, "flight_id": "UNKNOWN",
                "airline_key": airline_keys["UNKNOWN"], "route_key": UNKNOWN_ROUTE_KEY,
                "departure_date_key": None, "departure_ts": pd.NaT, "arrival_ts": pd.NaT,
                "duration_minutes": None, "is_overnight": None, "is_red_eye": None,
                "departure_hour": None, "was_corrected": False,
                "correction_reason": "quarantined_flight_placeholder",
            }
        ]
    )
    return pd.concat([unknown, fact], ignore_index=True)


def build_fact_booking(
    bookings: pd.DataFrame,
    fact_flight: pd.DataFrame,
    dim_passenger: pd.DataFrame,
    dim_status: pd.DataFrame,
) -> pd.DataFrame:
    flight_sks = dict(zip(fact_flight["flight_id"], fact_flight["flight_sk"]))
    passenger_sks = dict(zip(dim_passenger["passenger_id"], dim_passenger["passenger_sk"]))
    status_keys = dict(zip(dim_status["status"], dim_status["status_key"]))

    fact = bookings.sort_values("booking_id").reset_index(drop=True).copy()
    fact.insert(0, "booking_sk", range(1, len(fact) + 1))
    fact["flight_sk"] = fact["flight_id"].map(flight_sks).fillna(UNKNOWN_FLIGHT_SK).astype(int)
    fact["passenger_sk"] = fact["passenger_id"].map(passenger_sks)
    fact["status_key"] = fact["status_clean"].map(status_keys)
    fact["booking_date_key"] = fact["booking_date"].dt.strftime("%Y%m%d").astype(int)

    return fact[
        ["booking_sk", "booking_id", "flight_sk", "passenger_sk", "status_key", "booking_date_key",
         "seat_number"]
    ]


def build_fact_payment(payments: pd.DataFrame, fact_booking: pd.DataFrame) -> pd.DataFrame:
    booking_sks = dict(zip(fact_booking["booking_id"], fact_booking["booking_sk"]))

    fact = payments.sort_values("payment_id").reset_index(drop=True).copy()
    fact.insert(0, "payment_sk", range(1, len(fact) + 1))
    fact["booking_sk"] = fact["booking_id"].map(booking_sks)

    return fact[
        ["payment_sk", "payment_id", "booking_sk", "amount", "payment_method", "amount_quality"]
    ]


def build_model(silver: dict[str, pd.DataFrame], config: Config) -> dict[str, pd.DataFrame]:
    dim_date = build_dim_date(config)
    dim_airline = build_dim_airline(silver["flights"])
    dim_route = build_dim_route(silver["flights"])
    dim_status = build_dim_status(silver["bookings"])
    dim_passenger = build_dim_passenger(silver["passengers"])

    fact_flight = build_fact_flight(silver["flights"], dim_airline, dim_route)
    fact_booking = build_fact_booking(
        silver["bookings"], fact_flight, dim_passenger, dim_status
    )
    fact_payment = build_fact_payment(silver["payments"], fact_booking)

    model = {
        "dim_date": dim_date,
        "dim_airline": dim_airline,
        "dim_route": dim_route,
        "dim_status": dim_status,
        "dim_passenger": dim_passenger,
        "fact_flight": fact_flight,
        "fact_booking": fact_booking,
        "fact_payment": fact_payment,
    }
    for name, df in model.items():
        logger.info("modelled %s: %d rows", name, len(df))
    return model


def load_duckdb(model: dict[str, pd.DataFrame], config: Config) -> None:
    config.paths.warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.paths.warehouse))
    try:
        for ddl in ["01_dimensions.sql", "02_facts.sql"]:
            con.execute((config.paths.sql / ddl).read_text(encoding="utf-8"))

        for table in DIMENSION_ORDER + FACT_ORDER:
            df = model[table]
            con.register("staged", df)
            columns = ", ".join(f'"{c}"' for c in df.columns)
            con.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM staged")
            con.unregister("staged")

        con.execute((config.paths.sql / "03_kpi_views.sql").read_text(encoding="utf-8"))
        logger.info("loaded warehouse at %s", config.paths.warehouse)
    finally:
        con.close()
