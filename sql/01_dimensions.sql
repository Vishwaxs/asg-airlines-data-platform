-- Gold dimensions. Keys are declared here rather than only in pandas so the
-- grain and the referential contract are visible to anyone reading the
-- warehouse without reading the Python.

DROP TABLE IF EXISTS fact_payment;
DROP TABLE IF EXISTS fact_booking;
DROP TABLE IF EXISTS fact_flight;
DROP TABLE IF EXISTS dim_passenger;
DROP TABLE IF EXISTS dim_status;
DROP TABLE IF EXISTS dim_route;
DROP TABLE IF EXISTS dim_airline;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_date (
    date_key    INTEGER PRIMARY KEY,   -- YYYYMMDD
    date        DATE    NOT NULL,
    year        SMALLINT NOT NULL,
    quarter     TINYINT NOT NULL,
    month       TINYINT NOT NULL,
    month_name  VARCHAR NOT NULL,
    day         TINYINT NOT NULL,
    day_name    VARCHAR NOT NULL,
    week        TINYINT NOT NULL,
    is_weekend  BOOLEAN NOT NULL
);

CREATE TABLE dim_airline (
    airline_key  INTEGER PRIMARY KEY,
    airline_name VARCHAR NOT NULL UNIQUE,
    is_unknown   BOOLEAN NOT NULL
);

CREATE TABLE dim_route (
    route_key   INTEGER PRIMARY KEY,
    source      VARCHAR NOT NULL,
    destination VARCHAR NOT NULL,
    route_label VARCHAR NOT NULL UNIQUE
);

CREATE TABLE dim_status (
    status_key INTEGER PRIMARY KEY,
    status     VARCHAR NOT NULL UNIQUE,
    is_valid   BOOLEAN NOT NULL
);

-- passenger_sk is the truncated HMAC of the zero-padded Aadhaar, not a
-- sequence: it is stable across runs, so the dimension can be reloaded
-- without orphaning facts, and it carries no recoverable identity.
CREATE TABLE dim_passenger (
    passenger_sk VARCHAR PRIMARY KEY,
    passenger_id VARCHAR NOT NULL UNIQUE,
    age          SMALLINT,
    age_band     VARCHAR,
    gender       VARCHAR,
    masked_name  VARCHAR,
    masked_email VARCHAR,
    masked_phone VARCHAR,
    is_minor     BOOLEAN
);
