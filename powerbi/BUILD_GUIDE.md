# Power BI build guide

Click-by-click, assuming you have never opened this model. Budget 75 minutes. Everything loads
from `data/gold/*.csv`, which `python -m src.pipeline` produces.

Expected end state: four pages, three synced slicers, one inactive relationship, and headline
figures matching `reports/run_manifest.json` exactly.

---

## 1. Load the data (10 min)

**Home > Get data > Text/CSV.** Load exactly these ten files from `data/gold/`, in this order:

| # | File | Role |
|---|---|---|
| 1 | `dim_date.csv` | Date dimension |
| 2 | `dim_airline.csv` | Airline dimension |
| 3 | `dim_route.csv` | Route dimension |
| 4 | `dim_status.csv` | Booking status dimension |
| 5 | `dim_passenger.csv` | Passenger dimension |
| 6 | `fact_flight.csv` | Flight fact |
| 7 | `fact_booking.csv` | Booking fact |
| 8 | `fact_payment.csv` | Payment fact |
| 9 | `anomaly_summary.csv` | Disconnected, for page 4 |
| 10 | `dq_score.csv` | Disconnected, for page 4 |

Do **not** load the `v_*.csv` files. Those are the SQL versions of the same KPIs and exist so
you can check the report against the warehouse; loading them creates duplicate paths through
the model and ambiguous relationships.

In the Power Query preview, before clicking Load, check these types:

- `dim_date[date]` is Date, `dim_date[date_key]` is Whole Number.
- `fact_flight[departure_ts]`, `[arrival_ts]` are Date/Time.
- `fact_flight[duration_minutes]`, `fact_payment[amount]` are Decimal Number.
- `fact_flight[is_overnight]`, `[is_red_eye]`, `[was_corrected]`, `dim_status[is_valid]`,
  `dim_airline[is_unknown]`, `dim_passenger[is_minor]` are True/False.
- `fact_payment[amount]` keeps its blanks. If Power Query offers to replace errors with 0,
  refuse: 78 payments have no usable amount and a zero would corrupt every average.

Then **Transform data > Close & Apply**.

## 2. Relationships (10 min)

**Model view.** Power BI will have guessed some of these; delete anything it invented that is
not in this table, then create the rest by dragging.

| From (one) | To (many) | Cardinality | Cross-filter | Active |
|---|---|---|---|---|
| `dim_date[date_key]` | `fact_booking[booking_date_key]` | 1:* | Single | **Yes** |
| `dim_date[date_key]` | `fact_flight[departure_date_key]` | 1:* | Single | **No** |
| `dim_airline[airline_key]` | `fact_flight[airline_key]` | 1:* | Single | Yes |
| `dim_route[route_key]` | `fact_flight[route_key]` | 1:* | Single | Yes |
| `dim_status[status_key]` | `fact_booking[status_key]` | 1:* | Single | Yes |
| `dim_passenger[passenger_sk]` | `fact_booking[passenger_sk]` | 1:* | Single | Yes |
| `fact_flight[flight_sk]` | `fact_booking[flight_sk]` | 1:* | Single | Yes |
| `fact_booking[booking_sk]` | `fact_payment[booking_sk]` | 1:* | Single | Yes |

To make the flight-date relationship inactive: create it, double-click the line, untick **Make
this relationship active**, OK. It will render as a dashed line.

`anomaly_summary` and `dq_score` stay disconnected. That is deliberate; they are pre-aggregated
at a different grain and relating them would produce nonsense totals.

**Why the second date relationship is inactive:** bookings span twelve months and are the only
usable time axis; flights sit in four days of April 2026. One conformed date table serves both,
with `USERELATIONSHIP` activating the flight path per measure. The alternative, a second date
table, duplicates the calendar and breaks a shared slicer across pages.

## 3. Measures (10 min)

**Modeling > New table:** `Measures = {BLANK()}`. Hide its single column in report view. Add
every measure from `powerbi/measures.dax` to that table (Modeling > New measure, paste, Enter).

Sanity check as you go - these must match `reports/run_manifest.json`:

| Measure | Expected |
|---|---|
| Total Flights | 1,003 |
| Total Bookings | 1,000 |
| Total Passengers | 1,000 |
| Avg Duration (min) | 164.67 |
| Gross Revenue | 7,385,142.98 |
| Confirmed Revenue | 2,471,402.04 |
| Cancellation Rate | 31.40% |
| Payment Coverage % | 63.70% |

If Total Bookings reads 1,363, a relationship is filtering the wrong way: that is the payment
fan-out reaching the booking count.

## 4. Field formatting and hiding (5 min)

Set format strings: currency measures `#,0.00`; rate measures Percentage with 2 decimals;
duration measures `0.0`.

Hide from report view (they are keys, not fields anyone should drag onto a visual):
all `*_key` and `*_sk` columns on every table, `dim_passenger[passenger_id]`,
`fact_booking[booking_id]`, `fact_payment[payment_id]`, `fact_flight[flight_id]`.

Keep `fact_flight[flight_id]` visible only if you want it in the quarantine detail table on
page 4; otherwise hide it too.

Sort `dim_date[month_name]` by `dim_date[month]` (select the column, Column tools > Sort by
column) or months render alphabetically.

## 5. Slicers (5 min)

Put three slicers on page 1: **airline** (`dim_airline[airline_name]`), **route**
(`dim_route[route_label]`), **month** (`dim_date[month_name]`). Style: dropdown for airline and
route, tile for month.

Select all three, then **View > Sync slicers**. For each: tick Sync and Visible for pages 1-4.
Copy them to the same position on every page (top of the canvas, left-aligned) so they do not
move as you switch pages.

## 6. Colour rule

One accent colour for data, neutral greys for structure, red reserved exclusively for anomaly
and quarantine measures. Nothing else on any page is red - if everything is red, nothing reads
as a problem.

Set this once: **View > Customize current theme > Name and colors**, put the accent in colour 1
and greys in 2-4, then apply red per-visual only on page 4 and on the two anomaly cards on
page 1.

## 7. Page 1 - Executive Overview (10 min)

**Cards, top row (8 cards, or 2 rows of 4):** Total Flights, Total Bookings, Avg Duration (min),
Gross Revenue, Confirmed Revenue, Cancellation Rate, Anomaly Rate per 100 Rows, Data Quality
Score. The last two in red.

**Bookings trend by month.** Line chart. X axis `dim_date[month_name]` (sorted by `month`), Y
axis `[Total Bookings]`. This sits on `booking_date` through the active relationship.

Do not build a flights-per-day line chart anywhere. Flights span four days; it would have four
points and would read as an error.

**Flights by airline.** Bar chart (horizontal). Y axis `dim_airline[airline_name]`, X axis
`[Total Flights]`. Sort descending. The UNKNOWN bar is real and stays: 67 flights have no
usable airline and hiding it would overstate every carrier's share.

**Top 10 routes by traffic.** Bar chart. Y axis `dim_route[route_label]`, X `[Total Bookings]`,
Filter pane > Top N > Top 10 by `[Total Bookings]`.

## 8. Page 2 - Duration & Schedule (10 min)

**Avg duration by airline.** Bar chart, `dim_airline[airline_name]` by `[Avg Duration (min)]`.
Add `[Duration Sigma (min)]` to the tooltip.

**Avg duration by route with spread.** Table. Columns: `dim_route[route_label]`,
`[Total Flights]`, `[Avg Duration (min)]`, `[Duration Sigma (min)]`, `[Min Duration (min)]`,
`[Max Duration (min)]`. Sort by flights descending.

The spread matters: BOM-CCU alone runs 33 to 293 minutes across 90 flights, so a bare route
average would read as a scheduled block time this data does not support.

**Duration distribution.** Histogram: column chart on `fact_flight[duration_minutes]` binned.
Right-click the field > New group > Bin, size 15 minutes. X axis the bin, Y `[Total Flights]`.

**Departure-hour profile.** Column chart. X axis `fact_flight[departure_hour]`, Y
`[Total Flights]`. This is the flight time-profile that replaces a per-day trend.

**Cards:** Overnight Share, Red-eye Share, Overnight Flights, Red-eye Flights, Corrected
Flights. Overnight (departure date differs from arrival date) and red-eye (departs 22:00-04:59)
are different measures and both are shown; 122 flights are overnight, 271 are red-eye.

## 9. Page 3 - Route & Airline Performance (10 min)

**Route matrix.** Matrix visual. Rows `dim_route[route_label]`. Values: `[Total Flights]`,
`[Total Bookings]`, `[Avg Duration (min)]`, `[Duration Sigma (min)]`, `[Gross Revenue]`,
`[Cancellation Rate]`. Conditional formatting: data bars on Total Bookings, colour scale on
Cancellation Rate.

Route bookings sum to 998, not 1,000. The two missing bookings are on the quarantined `6F250`
and sit on the unknown flight member, which has no route. That is correct and worth saying out
loud rather than patching.

**Airline share.** Donut: legend `dim_airline[airline_name]`, values `[Total Flights]`.

**Source to destination flow.** Matrix: rows `dim_route[source]`, columns
`dim_route[destination]`, values `[Total Bookings]`. All 30 ordered pairs are populated and
there are no self-routes, so the diagonal is empty by design.

**Bookings per flight.** Card with `[Bookings per Flight]`, plus a bar chart of
`[Bookings per Flight]` by `dim_airline[airline_name]`.

## 10. Page 4 - Data Quality & Anomalies (10 min)

Red is allowed on this page and only this page.

**Anomaly counts by type.** Bar chart. Y `anomaly_summary[anomaly]`, X `[Anomaly Incidences]`,
sorted descending. Add `anomaly_summary[rate_pct]` to the tooltip so the reader sees the rate
against the right denominator.

**DQ score by table.** Column chart. X `dq_score[table]`, Y `[Data Quality Score]`. Set the Y
axis to start at 0.8 so the differences are visible, and label the axis so the truncation is
explicit.

**Row-count waterfall.** Waterfall visual. Category `dq_score[table]`, Y `[Rows Retained]`;
or a clustered column of `[Rows Ingested]`, `[Rows Flagged]`, `[Rows Collapsed]`,
`[Rows Quarantined]`, `[Rows Retained]` per table, which is easier to read and shows that
4,059 rows in becomes 4,003 rows retained with 2 quarantined and 54 collapsed.

**Missing versus sentinel breakdown.** Clustered column. Load nothing new: use
`[Missing Amount Payments]` and `[Non-numeric Amount Payments]` as two series, and add
`[Invalid Status Bookings]`. A null and a literal "INVALID" are different upstream failures
and the visual should keep them apart.

**Quarantine detail table.** Table visual over `data/quarantine/flights.csv`. Load that file as
an eleventh table (it stays disconnected). Columns: flight_id, source, destination,
departure_ts, arrival_ts, quarantine_reason. Two rows, both `6F250`, both
`conflicting_duplicate_key`.

**Cards:** Rows Quarantined, Bookings on Quarantined Flight (2), Corrected Flights (1),
Unusable Amount Payments (78).

## 11. Screenshots (5 min)

Export each page at 1920px wide into `powerbi/screenshots/`, named
`01_executive_overview.png`, `02_duration_schedule.png`, `03_route_airline.png`,
`04_data_quality.png`.

Fastest route: set the canvas to 16:9, then **File > Export > Export to PDF** and crop, or use
the Windows snipping tool at full-window width on a 1920px display. The documentation generator
picks these up by filename.

## Final check

Compare against `reports/run_manifest.json`:

- Total Flights 1,003, Total Bookings 1,000, Total Passengers 1,000.
- Gross Revenue 7,385,142.98 and Confirmed Revenue 2,471,402.04 - both, never one alone.
- Cancellation Rate 31.40%, Payment Coverage 63.70%.
- No flights-per-day trend line anywhere.
- Red appears only on page 4 and the two anomaly cards on page 1.
