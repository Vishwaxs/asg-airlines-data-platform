-- KPI views over the star schema. Revenue is always taken from fact_payment
-- at payment grain and joined no further than fact_booking; every view here
-- can be reproduced in Power BI by the measures in powerbi/measures.dax.

CREATE OR REPLACE VIEW v_flight_summary AS
SELECT
    COUNT(*)                                        AS flights,
    ROUND(AVG(duration_minutes), 2)                 AS avg_duration_minutes,
    ROUND(STDDEV_SAMP(duration_minutes), 2)         AS stddev_duration_minutes,
    MIN(duration_minutes)                           AS min_duration_minutes,
    MAX(duration_minutes)                           AS max_duration_minutes,
    SUM(CASE WHEN is_overnight THEN 1 ELSE 0 END)   AS overnight_flights,
    SUM(CASE WHEN is_red_eye THEN 1 ELSE 0 END)     AS red_eye_flights,
    SUM(CASE WHEN was_corrected THEN 1 ELSE 0 END)  AS corrected_flights
FROM fact_flight
WHERE flight_sk <> -1;

CREATE OR REPLACE VIEW v_flights_by_airline AS
SELECT
    a.airline_name,
    a.is_unknown,
    COUNT(*)                                                       AS flights,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)             AS share_pct,
    ROUND(AVG(f.duration_minutes), 2)                              AS avg_duration_minutes,
    ROUND(STDDEV_SAMP(f.duration_minutes), 2)                      AS stddev_duration_minutes
FROM fact_flight f
JOIN dim_airline a ON a.airline_key = f.airline_key
WHERE f.flight_sk <> -1
GROUP BY a.airline_name, a.is_unknown
ORDER BY flights DESC;

-- Route duration is reported with its spread: within BOM-CCU alone durations
-- run 33-293 minutes, so a bare average would read as a scheduled block time
-- the data does not support.
--
-- Each metric is aggregated at its own grain in its own CTE before the join.
-- Averaging duration across a flight-to-booking join would weight every
-- flight by how many bookings it carried.
CREATE OR REPLACE VIEW v_route_performance AS
WITH flight_stats AS (
    SELECT
        route_key,
        COUNT(*)                                AS flights,
        ROUND(AVG(duration_minutes), 2)         AS avg_duration_minutes,
        ROUND(STDDEV_SAMP(duration_minutes), 2) AS stddev_duration_minutes,
        MIN(duration_minutes)                   AS min_duration_minutes,
        MAX(duration_minutes)                   AS max_duration_minutes
    FROM fact_flight
    WHERE flight_sk <> -1
    GROUP BY route_key
),
booking_stats AS (
    SELECT
        f.route_key,
        COUNT(*)                                                AS bookings,
        SUM(CASE WHEN s.status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_bookings
    FROM fact_booking b
    JOIN fact_flight f  ON f.flight_sk = b.flight_sk
    JOIN dim_status s   ON s.status_key = b.status_key
    WHERE f.flight_sk <> -1
    GROUP BY f.route_key
),
revenue_stats AS (
    SELECT
        f.route_key,
        ROUND(SUM(p.amount), 2) AS revenue
    FROM fact_payment p
    JOIN fact_booking b ON b.booking_sk = p.booking_sk
    JOIN fact_flight f  ON f.flight_sk = b.flight_sk
    WHERE f.flight_sk <> -1
    GROUP BY f.route_key
)
SELECT
    r.route_label,
    r.source,
    r.destination,
    fs.flights,
    COALESCE(bs.bookings, 0)                                            AS bookings,
    fs.avg_duration_minutes,
    fs.stddev_duration_minutes,
    fs.min_duration_minutes,
    fs.max_duration_minutes,
    rs.revenue,
    ROUND(100.0 * bs.cancelled_bookings / NULLIF(bs.bookings, 0), 2)    AS cancellation_rate_pct
FROM flight_stats fs
JOIN dim_route r          ON r.route_key = fs.route_key
LEFT JOIN booking_stats bs ON bs.route_key = fs.route_key
LEFT JOIN revenue_stats rs ON rs.route_key = fs.route_key
ORDER BY bookings DESC;

CREATE OR REPLACE VIEW v_departure_hour_profile AS
SELECT
    departure_hour,
    COUNT(*)                                                       AS flights,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)             AS share_pct,
    BOOL_OR(is_red_eye)                                            AS is_red_eye_hour
FROM fact_flight
WHERE flight_sk <> -1
GROUP BY departure_hour
ORDER BY departure_hour;

CREATE OR REPLACE VIEW v_booking_status AS
SELECT
    s.status,
    s.is_valid,
    COUNT(*)                                           AS bookings,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM fact_booking b
JOIN dim_status s ON s.status_key = b.status_key
GROUP BY s.status, s.is_valid
ORDER BY bookings DESC;

CREATE OR REPLACE VIEW v_bookings_monthly AS
SELECT
    d.year,
    d.month,
    d.month_name,
    COUNT(*)                                                              AS bookings,
    SUM(CASE WHEN s.status = 'CONFIRMED' THEN 1 ELSE 0 END)               AS confirmed,
    SUM(CASE WHEN s.status = 'CANCELLED' THEN 1 ELSE 0 END)               AS cancelled
FROM fact_booking b
JOIN dim_date d   ON d.date_key = b.booking_date_key
JOIN dim_status s ON s.status_key = b.status_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

-- Gross is cash observed against any booking; confirmed is the recognised
-- subset. Both are reported because 306 payments sit against CANCELLED
-- bookings and neither figure alone answers "what did we earn".
CREATE OR REPLACE VIEW v_revenue_summary AS
SELECT
    ROUND(SUM(p.amount), 2)                                                AS gross_revenue,
    ROUND(SUM(CASE WHEN s.status = 'CONFIRMED' THEN p.amount END), 2)      AS confirmed_revenue,
    ROUND(SUM(CASE WHEN s.status = 'CANCELLED' THEN p.amount END), 2)      AS cancelled_revenue,
    COUNT(*)                                                               AS payments,
    COUNT(p.amount)                                                        AS payments_with_amount,
    COUNT(DISTINCT p.booking_sk)                                           AS bookings_paid
FROM fact_payment p
JOIN fact_booking b ON b.booking_sk = p.booking_sk
JOIN dim_status s   ON s.status_key = b.status_key;

CREATE OR REPLACE VIEW v_route_revenue AS
SELECT
    r.route_label,
    COUNT(DISTINCT b.booking_sk)             AS bookings,
    ROUND(SUM(p.amount), 2)                  AS revenue,
    ROUND(AVG(p.amount), 2)                  AS avg_payment
FROM fact_payment p
JOIN fact_booking b ON b.booking_sk = p.booking_sk
JOIN fact_flight f  ON f.flight_sk = b.flight_sk
JOIN dim_route r    ON r.route_key = f.route_key
WHERE f.flight_sk <> -1
GROUP BY r.route_label
ORDER BY revenue DESC NULLS LAST;

CREATE OR REPLACE VIEW v_payment_quality AS
SELECT
    amount_quality,
    COUNT(*)                                           AS payments,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
    ROUND(SUM(amount), 2)                              AS amount
FROM fact_payment
GROUP BY amount_quality
ORDER BY payments DESC;

CREATE OR REPLACE VIEW v_passenger_profile AS
SELECT
    age_band,
    gender,
    COUNT(*)                                          AS passengers,
    SUM(CASE WHEN is_minor THEN 1 ELSE 0 END)         AS minors
FROM dim_passenger
GROUP BY age_band, gender
ORDER BY age_band, gender;

-- Booking counts are taken from fact_booking alone. Counting them across a
-- join to fact_payment returns 1,363 rather than 1,000, because 637 bookings
-- carry 1,000 payments - the same fan-out that inflates naive revenue by
-- 208,615.94. Payment coverage is therefore its own aggregate.
CREATE OR REPLACE VIEW v_kpi_headline AS
WITH f AS (SELECT * FROM v_flight_summary),
     r AS (SELECT * FROM v_revenue_summary),
     b AS (
        SELECT
            COUNT(*)                                                       AS bookings,
            SUM(CASE WHEN s.status = 'CANCELLED' THEN 1 ELSE 0 END)        AS cancelled,
            SUM(CASE WHEN s.status = 'CONFIRMED' THEN 1 ELSE 0 END)        AS confirmed
        FROM fact_booking b
        JOIN dim_status s ON s.status_key = b.status_key
     ),
     cov AS (
        SELECT COUNT(DISTINCT booking_sk) AS bookings_with_payment FROM fact_payment
     )
SELECT
    f.flights,
    b.bookings,
    (SELECT COUNT(*) FROM dim_passenger)                                   AS passengers,
    f.avg_duration_minutes,
    f.stddev_duration_minutes,
    r.gross_revenue,
    r.confirmed_revenue,
    ROUND(100.0 * b.cancelled / b.bookings, 2)                             AS cancellation_rate_pct,
    ROUND(100.0 * b.confirmed / b.bookings, 2)                             AS confirmation_rate_pct,
    ROUND(100.0 * cov.bookings_with_payment / b.bookings, 2)               AS payment_coverage_pct,
    ROUND(r.gross_revenue / NULLIF(r.bookings_paid, 0), 2)                 AS avg_ticket_value_per_booking,
    ROUND(1.0 * b.bookings / NULLIF(f.flights, 0), 3)                      AS bookings_per_flight,
    ROUND(100.0 * f.red_eye_flights / f.flights, 2)                        AS red_eye_share_pct,
    ROUND(100.0 * f.overnight_flights / f.flights, 2)                      AS overnight_share_pct
FROM f, r, b, cov;
