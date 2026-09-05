# Data quality report

Run covers 4,059 ingested rows across four source sheets.

## Scores

`dq_score = 1 - (quarantined + flagged) / ingested`

A flagged row is one carrying a quality defect but still usable: a missing or sentinel
airline, a corrected duration, an invalid status, an unusable amount, a truncated Aadhaar.
Flagged rows are retained. Quarantined rows are removed from the facts because they are
ambiguous rather than merely incomplete. Collapsed rows are byte-identical duplicates.

| table      |   ingested |   flagged |   quarantined |   collapsed_duplicates |   retained |   dq_score |
|:-----------|-----------:|----------:|--------------:|-----------------------:|-----------:|-----------:|
| flights    |       1020 |        68 |             2 |                     15 |       1003 |     0.9314 |
| bookings   |       1000 |        75 |             0 |                      0 |       1000 |     0.925  |
| payments   |       1000 |        78 |             0 |                      0 |       1000 |     0.922  |
| passengers |       1039 |       107 |             0 |                     39 |       1000 |     0.897  |

## Anomaly taxonomy

There is no delay measure here. The workbook carries no scheduled-versus-actual timestamp
pair, so on-time performance is not computable from it; `scheduled_departure` and
`actual_departure` are the two columns that would be required. What is computable is an
anomaly rate, defined per source table below.

| anomaly                       | scope_table   |   count |   scope_rows |   rate_pct |
|:------------------------------|:--------------|--------:|-------------:|-----------:|
| aadhaar_length_anomaly        | passengers    |     114 |         1039 |     10.972 |
| booking_on_quarantined_flight | bookings      |       2 |         1000 |      0.2   |
| booking_without_payment       | bookings      |     363 |         1000 |     36.3   |
| conflicting_duplicate_key     | flights       |       2 |         1020 |      0.196 |
| duplicate_passenger_id        | passengers    |      75 |         1039 |      7.218 |
| exact_duplicate               | flights       |      15 |         1020 |      1.471 |
| flight_without_booking        | flights       |      20 |         1020 |      1.961 |
| missing_airline               | flights       |      41 |         1020 |      4.02  |
| missing_amount                | payments      |      48 |         1000 |      4.8   |
| missing_last_name             | passengers    |      10 |         1039 |      0.962 |
| missing_status                | bookings      |      45 |         1000 |      4.5   |
| negative_duration             | flights       |       1 |         1020 |      0.098 |
| non_numeric_amount            | payments      |      30 |         1000 |      3     |
| sentinel_airline              | flights       |      31 |         1020 |      3.039 |
| sentinel_status               | bookings      |      30 |         1000 |      3     |
| uncorrectable_duration        | flights       |       0 |         1020 |      0     |

Total anomaly incidences: 827 across 4,059 ingested rows (20.37 per 100 rows). A single row can carry
more than one anomaly, so this is an incidence rate, not a share of rows.

## Duration reconciliation

Recomputed duration (`arrival_ts - departure_ts`) is checked against the source `duration`
column, which is treated as an independent witness rather than as the authoritative value.

- source values parseable: 1020 of 1020
- mismatches before correction: 1 (max absolute delta 1440 minutes)
- mismatches after correction: 0 (max absolute delta 0.005 minutes)

The single pre-correction mismatch is SJ192, off by exactly 1,440 minutes - one day. The
raw duration column reads 05:00:00 for that row and the rolled-forward arrival gives
exactly 300 minutes, so two independent sources agree on the corrected value.

## Headline figures

- flights modelled: 1,003
- bookings modelled: 1,000
- passengers modelled: 1,000
- average duration: 164.67 minutes (sigma 77.39)
- gross revenue: 7,385,142.98
- confirmed revenue: 2,471,402.04
- cancellation rate: 31.40%
- payment coverage: 63.70%

## Passenger survivorship

75 candidate rows across 36 duplicated passenger ids were resolved to one surviving row each. Every candidate and the reason its winner was chosen is in
`reports/passenger_survivorship.csv`. Selection order: fewest nulls, then a full 12-digit
Aadhaar, then the lexicographically smallest email. No group was resolved by row order.

| reason              |   groups |
|:--------------------|---------:|
| lowest_email        |       21 |
| fewest_nulls        |       10 |
| aadhaar_full_length |        5 |

