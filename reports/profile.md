# Source profile — verification

Every figure below was recomputed directly from `data/raw/UseCase_Airlines.xlsx` (pandas 3.0.5,
openpyxl reader) rather than assumed from the brief. Where a stated figure could not be reproduced
exactly, the discrepancy is called out rather than silently corrected.

## flights (1020 rows x 7 cols)

- `airline`: IndiGo 249, SpiceJet 240, Air India 236, Vistara 223, null 41, literal `"UNKNOWN"` 31.
- `flight_id`: 1,004 unique of 1,020. 16 ids duplicated. 15 are byte-identical duplicate rows
  (`AI020 AI031 AI043 AI070 AI242 SJ037 SJ118 SJ142 SJ146 UK013 UK049 UK139 UK160 UK163 UK180`).
  `6F250` conflicts: one row departs DEL at 03:26:41.701 arriving BLR 07:30:41.701 (duration
  04:04:00), the other departs CCU at 02:23:41.702 arriving BLR 02:56:41.702 (duration 00:33:00) —
  different source city and different timestamps, not a data-entry echo.
- `source`/`destination`: 6 cities (BLR BOM CCU DEL HYD MAA), all 30 ordered pairs present, 0
  self-routes.
- `departure_time` spans 2026-04-17 12:25:41.701 to 2026-04-20 23:38:41.701 (4 calendar days).
  125 rows have `departure_time.date() != arrival_time.date()`.
- `duration` column: 1,019 values are Python `datetime.time`, exactly one (`SJ192`, source row
  index 355) is `datetime.datetime(1899, 12, 29, 5, 0)` — Excel's negative-duration artefact.
  `pd.to_timedelta` raises `OutOfBoundsTimedelta` on that value.
- `SJ192` is the only row where `arrival_time < departure_time`: departs 2026-04-19 18:45:42,
  arrives 2026-04-18 23:45:42 -> -1,140 minutes raw. Adding one day to `arrival_time` gives exactly
  300 minutes, which matches the raw `duration` cell (`05:00:00`) for that row exactly. This
  corroboration (an independent column agreeing with the corrected value) is why the fix is a
  reconciliation, not a guess.
- Rows with `microsecond == 0` on `departure_time`: `6F026, 6F176, SJ192, UK122` (4 rows), against
  `.70x` microseconds for every other row — consistent with deliberately injected/edited records.

## bookings (1000 rows x 9 cols)

- `status`: CONFIRMED 320, CANCELLED 314, PENDING 291, null 45, literal `"INVALID"` 30.
- `booking_id` unique, 0 exact duplicate rows.
- `booking_date` spans 2025-04-17 11:37:36.951 to 2026-04-17 11:37:36.951, **342 distinct calendar
  dates**, touching **13 distinct calendar month-buckets** (Apr 2025 through Apr 2026 inclusive).
  **Discrepancy noted:** the brief states "12 months" — that is correct as elapsed duration
  (exactly 12 months + 1 day) but the span touches 13 distinct `YYYY-MM` buckets. Both framings are
  defensible; `dim_date.month`/`month_name` will show 13 populated months and that is expected, not
  a bug.
- 0 orphan `flight_id`, 0 orphan `passenger_id`.
- 32 bookings reference one of the 16 duplicated flight_ids; 2 of those reference `6F250`.
- `passport_number` matches `^[A-Z]\d{7}$` on 100% of rows; `emergency_contact_phone` matches
  `^\+91-\d{10}$` on 100% of rows. 0 duplicate `(flight_id, seat_number)` pairs.

## payments (1000 rows x 4 cols)

- `amount` Python types: float 961, str 30, int 9. All 30 strings are the literal `"INVALID"`.
  Plus 48 true nulls -> 78 of 1,000 rows cannot contribute to revenue.
- Valid (numeric) amounts: 922 rows, min 1,002.59, max 14,992.95, **sum 7,385,142.98**.
- 1,000 payment rows across 637 distinct `booking_id`s: 370 bookings with 1 payment, 189 with 2,
  63 with 3, 13 with 4, 1 with 5, 1 with 6. 363 bookings have no payment row at all.
- 306 payments sit against a CANCELLED booking. 0 orphan `booking_id`.
- `payment_method`: UPI 358, CARD 329, NETBANKING 313, 0 nulls.

## passengers (1039 rows x 9 cols)

- 1,000 unique `passenger_id`, 0 byte-identical duplicate rows. 36 ids duplicated (33 groups of 2,
  3 groups of 3).
- Within duplicate groups: `age` and `gender` never vary (0 of 36 groups). `first_name` varies in
  11 of 36 groups, `last_name` in 17. `email`, `phone`, `aadhaar_id`, `date_of_birth` vary in **all
  36** groups. `drop_duplicates()` would pick an arbitrary survivor and is not a defensible rule.
- `last_name` null in 10 rows. `age` ranges 1-89, 227 rows under 18.
- `phone` matches `^\+91-\d{10}$` on 100% of rows. `gender` is `M`/`F` only, 0 nulls.
- `aadhaar_id` stored as `int64`, string length after cast: 12 digits (925), 11 digits (109), 10
  digits (5). Aadhaar is always 12 digits, so 114 rows lost leading zeros to integer typing upstream.
- 382 passengers have no booking.

## Cross-table fan-out (reproduced with LEFT JOIN so unmatched rows are visible, matching how an
analyst would naively write the query in SQL/Power Query)

```
bookings LEFT JOIN flights                    1000 -> 1032 rows   (16 duplicate flight_id keys)
bookings LEFT JOIN payments                   1000 -> 1363 rows   (637 bookings carry 1000 payments)
bookings LEFT JOIN flights LEFT JOIN payments  1000 -> 1404 rows
naive SUM(amount) on that join                  7,593,758.92
true SUM(payments.amount)                       7,385,142.98
inflation                                         208,615.94   (+2.82%)
```

Confirmed-only revenue (payments joined to bookings with `status == 'CONFIRMED'`): **2,471,402.04**.

flights with no matching booking: 20. passengers with no booking: 382.

## Verdict

Every quantitative claim in the brief re-verified exactly except the "12 months" framing of the
booking-date span, which is a reasonable rounding rather than an error (noted above). All other
counts, sums, and the ₹208,615.94 fan-out inflation reproduce bit-for-bit.
