-- Facts. Three grains, stated explicitly:
--   fact_flight  : one row per surviving flight_id
--   fact_booking : one row per booking_id
--   fact_payment : one row per payment_id
--
-- fact_payment references fact_booking and never fact_flight. Joining
-- payments to flights directly reproduces the 1,404-row cartesian fan-out
-- that inflates revenue by 208,615.94, because 637 bookings carry 1,000
-- payments and 16 flight_ids appeared twice in the source.

CREATE TABLE fact_flight (
    flight_sk          INTEGER PRIMARY KEY,
    flight_id          VARCHAR NOT NULL,
    airline_key        INTEGER NOT NULL REFERENCES dim_airline(airline_key),
    route_key          INTEGER REFERENCES dim_route(route_key),
    departure_date_key INTEGER REFERENCES dim_date(date_key),
    departure_ts       TIMESTAMP,
    arrival_ts         TIMESTAMP,
    duration_minutes   DOUBLE,
    is_overnight       BOOLEAN,
    is_red_eye         BOOLEAN,
    departure_hour     TINYINT,
    was_corrected      BOOLEAN,
    correction_reason  VARCHAR
);

CREATE TABLE fact_booking (
    booking_sk       INTEGER PRIMARY KEY,
    booking_id       VARCHAR NOT NULL UNIQUE,
    flight_sk        INTEGER NOT NULL REFERENCES fact_flight(flight_sk),
    passenger_sk     VARCHAR NOT NULL REFERENCES dim_passenger(passenger_sk),
    status_key       INTEGER NOT NULL REFERENCES dim_status(status_key),
    booking_date_key INTEGER REFERENCES dim_date(date_key),
    seat_number      VARCHAR
);

CREATE TABLE fact_payment (
    payment_sk     INTEGER PRIMARY KEY,
    payment_id     VARCHAR NOT NULL UNIQUE,
    booking_sk     INTEGER NOT NULL REFERENCES fact_booking(booking_sk),
    amount         DOUBLE,
    payment_method VARCHAR,
    amount_quality VARCHAR NOT NULL
);
