# Assumptions

Each assumption states the evidence behind it. Where the evidence was ambiguous, the choice is
recorded along with what would change it.

## 1. A negative duration is a date that failed to roll over at midnight

`SJ192` departs 2026-04-19 18:45:42 and arrives 2026-04-18 23:45:42, giving -1,140 minutes.
Adding one day to the arrival gives exactly 300 minutes. The source `duration` column holds
`05:00:00` for that row, which is 300 minutes.

Two independent fields agree on the corrected value, so the correction is treated as a
reconciliation. It is applied only when the recomputed duration is negative, is recorded in
`was_corrected` and `correction_reason`, and is reported in the data quality report. If the
correction still leaves a negative duration, or one longer than 24 hours, the row is
quarantined rather than corrected again.

## 2. The source `duration` column is a witness, not the authority

Duration is always recomputed from `arrival_ts - departure_ts`. The source column is parsed
only to reconcile against, because it is a mixed-type object column (1,019 `datetime.time`
values and one `datetime.datetime`) that `pd.to_timedelta` cannot read, and because a stored
duration cannot be trusted over the timestamps it is meant to describe.

27 values carry fractional seconds (`02:00:00.298000`), which the parser tolerates. The
reconciliation therefore uses a half-minute tolerance; the only mismatch found is SJ192, at
exactly 1,440 minutes.

## 3. Two duplicate-key situations need two different treatments

For flights, 15 of the 16 duplicated `flight_id`s are byte-identical rows (verified by
comparing the bronze `_row_hash` within each key group). A repeated identical row carries no
new information, so one copy is kept. `6F250` has two rows disagreeing on source city and both
timestamps; there is no field in the data that arbitrates between them, so both rows are
quarantined and the id is excluded from `fact_flight`.

For passengers, no duplicate group is byte-identical and all 36 conflict on email, phone,
Aadhaar and date of birth, so quarantining them all would discard 36 real passengers. A
deterministic survivorship rule is applied instead.

## 4. Passenger survivorship order: fewest nulls, then full Aadhaar, then lowest email

Applied in that order and logged per candidate row in `reports/passenger_survivorship.csv`.
The reasoning: a row with fewer nulls carries more information; an Aadhaar that kept its 12
digits is the less corrupted record; and the email tie-break exists only to make the outcome
deterministic rather than dependent on row order. Across the 36 groups the rule resolved 10 by
null count, 5 by Aadhaar length and 21 by email.

`age` and `gender` never vary within a group, so no group is resolved on a demographic field.

## 5. Bookings survive their flight being quarantined

The two bookings referencing `6F250` are kept and point at an unknown member,
`fact_flight.flight_sk = -1`. Dropping them would make booking counts disagree with the source
for a reason unrelated to bookings. They are excluded from route and airline rollups, which is
why route bookings sum to 998 rather than 1,000.

## 6. A null and a sentinel are different upstream failures

`airline` has 41 nulls and 31 rows of the literal `"UNKNOWN"`; `status` has 45 nulls and 30 of
`"INVALID"`; `amount` has 48 nulls and 30 of `"INVALID"`. Each pair is mapped to the same
analytical bucket so reporting stays simple, but counted separately in the data quality report,
because a value that was never captured and a value that was captured wrongly point at
different problems in the source system.

`payments.amount` is classified as `valid`, `missing` or `non_numeric`. Rows stay in
`fact_payment` with a null amount so payment counts remain accurate. Filling with zero would
corrupt every average, because a zero payment and an unknown payment are not the same fact.

## 7. Nothing merely incomplete is deleted

Quarantine is reserved for rows that are structurally unusable or genuinely ambiguous:
conflicting duplicate keys, uncorrectable durations, schema violations. A booking with an
unusable status is still a booking; a passenger with no surname is still a passenger. This is a
governance decision, not an oversight: 2 rows of 4,059 are quarantined, and everything else is
flagged and retained.

## 8. Aadhaar is 12 digits and lost leading zeros to numeric typing

925 values are 12 digits, 109 are 11, 5 are 10. Aadhaar numbers are always 12 digits, so the
shorter values are the same identifiers with leading zeros stripped by int64 storage upstream.
Every value is cast to string and zero-padded to 12 before hashing. Without that step the same
person hashes to two different surrogate keys.

The alternative reading, that these are simply invalid numbers, was rejected: the length
distribution (a long tail at exactly 11 and 10 digits, nothing shorter) is the signature of
integer typing, not of data entry error.

## 9. Revenue has two correct answers and both are reported

Gross revenue (7,385,142.98) is every valid payment. Confirmed revenue (2,471,402.04) is the
subset against CONFIRMED bookings. 306 payments sit against CANCELLED bookings, so neither
figure alone answers "what did we earn": gross is cash observed, confirmed is revenue
recognised. Reporting one without the other would be misleading in either direction.

## 10. Delay is not computable and is not invented

The brief asks for delay analysis. The workbook has no `scheduled_departure` or
`actual_departure`, only one departure timestamp per flight, so there is nothing to difference.
An anomaly taxonomy with per-table rates is reported instead. Adding those two columns to the
source is the entire fix.

## 11. Route duration describes the data, not a schedule

Within BOM-CCU alone, durations run 33 to 293 minutes across 90 flights. Duration is therefore
reported as mean with standard deviation and min/max, never as a point estimate, and route
averages should not be read as scheduled block times. The durations in this dataset are not a
deterministic function of the route.

## 12. `booking_date` is the only usable time axis

Bookings span 2025-04-17 to 2026-04-17 across 342 distinct dates; flights span four days in
April 2026. Any trend visual sits on `booking_date`. Flights are profiled by departure hour
instead. A flights-per-day line chart would have four points on it.

The brief describes the booking span as twelve months. That is correct as elapsed time (twelve
months and one day) but it touches 13 distinct calendar month buckets, so `dim_date` shows 13
populated months. Both readings are defensible; the discrepancy is noted rather than smoothed.

## 13. Microsecond-zero rows are injected records, and are left alone

Four rows (`6F026`, `6F176`, `SJ192`, `UK122`) have `microsecond == 0` on their departure
timestamp against `.70x` for every other row, which suggests they were edited or inserted
deliberately into an otherwise machine-generated file. Only SJ192 is defective on its own
terms; the other three are internally consistent and are processed normally. The observation is
recorded because it explains where the defects came from, but provenance is not a reason to
drop otherwise valid rows.
