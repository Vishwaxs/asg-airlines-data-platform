import sys
sys.path.insert(0, ".")
import duckdb
import pandas as pd
import numpy as np

excel_path = "data/raw/UseCase_Airlines.xlsx"
flights_raw = pd.read_excel(excel_path, sheet_name="flights")
bookings_raw = pd.read_excel(excel_path, sheet_name="bookings")
payments_raw = pd.read_excel(excel_path, sheet_name="payments")
passengers_raw = pd.read_excel(excel_path, sheet_name="passengers")

con = duckdb.connect("warehouse/asg_airlines.duckdb", read_only=True)
headline = con.execute("SELECT * FROM v_kpi_headline").df().iloc[0].to_dict()
print("v_kpi_headline values:")
for k, v in headline.items():
    print(f"  {k}: {v}")

# 1. Average duration
# What is the scope of flights? fact_flight where flight_sk <> -1 (1003 rows)
fact_f = con.execute("SELECT duration_minutes FROM fact_flight WHERE flight_sk <> -1").df()
my_avg_dur = round(fact_f["duration_minutes"].mean(), 2)
my_std_dur = round(fact_f["duration_minutes"].std(ddof=1), 2)
print(f"\nDuration: headline avg={headline['avg_duration_minutes']}, measured={my_avg_dur}")
print(f"Duration: headline std={headline['stddev_duration_minutes']}, measured={my_std_dur}")

# 2. Cancellation rate & Confirmation rate
# Denominator: total bookings in fact_booking (1000)
# Or valid status bookings? (320 + 314 + 291 = 925)
total_b = len(bookings_raw)
cancelled_b = (bookings_raw["status"] == "CANCELLED").sum()
confirmed_b = (bookings_raw["status"] == "CONFIRMED").sum()

rate_cancel_all = round(100.0 * cancelled_b / total_b, 2)
rate_cancel_valid = round(100.0 * cancelled_b / 925, 2)
rate_confirm_all = round(100.0 * confirmed_b / total_b, 2)
rate_confirm_valid = round(100.0 * confirmed_b / 925, 2)
print(f"\nCancellation rate: headline={headline['cancellation_rate_pct']}%")
print(f"  measured (over all 1000 bookings): {rate_cancel_all}%")
print(f"  measured (over 925 valid bookings): {rate_cancel_valid}%")

print(f"Confirmation rate: headline={headline['confirmation_rate_pct']}%")
print(f"  measured (over all 1000 bookings): {rate_confirm_all}%")
print(f"  measured (over 925 valid bookings): {rate_confirm_valid}%")

# Check documentation on denominator for cancellation rate:
# In docs/ASSUMPTIONS.md: what does it say?

# 3. Gross and confirmed revenue
valid_p = payments_raw[pd.to_numeric(payments_raw["amount"], errors="coerce").notna()].copy()
valid_p["amount_num"] = pd.to_numeric(valid_p["amount"])
my_gross = round(valid_p["amount_num"].sum(), 2)
print(f"\nGross revenue: headline={headline['gross_revenue']}, measured={my_gross}")

# Confirmed revenue:
p_b = payments_raw.merge(bookings_raw, on="booking_id")
p_b_num = p_b[pd.to_numeric(p_b["amount"], errors="coerce").notna()].copy()
p_b_num["amount_num"] = pd.to_numeric(p_b_num["amount"])
my_confirmed_rev = round(p_b_num[p_b_num["status"] == "CONFIRMED"]["amount_num"].sum(), 2)
print(f"Confirmed revenue: headline={headline['confirmed_revenue']}, measured={my_confirmed_rev}")

# 4. Average ticket value
# Check denominator in v_kpi_headline:
# ROUND(r.gross_revenue / NULLIF(r.bookings_paid, 0), 2) AS avg_ticket_value_per_booking
# r.bookings_paid = COUNT(DISTINCT p.booking_sk)
# Wait! How many bookings have valid payments?
# Let's check:
distinct_bookings_paid = con.execute("""
    SELECT COUNT(DISTINCT p.booking_sk) 
    FROM fact_payment p 
    JOIN fact_booking b ON b.booking_sk = p.booking_sk
""").df().values[0][0]
# Wait, in v_revenue_summary:
# COUNT(DISTINCT p.booking_sk) AS bookings_paid
# Does p.booking_sk count all payments or only payments with valid amount?
# Let's check SQL for v_revenue_summary!
# In 03_kpi_views.sql:
# COUNT(DISTINCT p.booking_sk) AS bookings_paid
# Notice: p is fact_payment. Even if p.amount is NULL, p.booking_sk is not NULL!
# Are there bookings where ALL payments are invalid/null?
# Let's check!
bids_with_any_payment = payments_raw["booking_id"].nunique() # 637
bids_with_valid_payment = valid_p["booking_id"].nunique()
print(f"\nAverage ticket value: headline={headline['avg_ticket_value_per_booking']}")
print(f"  distinct bookings in payments (including null/invalid): {bids_with_any_payment}")
print(f"  distinct bookings with at least one VALID payment: {bids_with_valid_payment}")
print(f"  gross / bids_with_any_payment: {my_gross / bids_with_any_payment:.2f}")
print(f"  gross / bids_with_valid_payment: {my_gross / bids_with_valid_payment:.2f}")

# 5. Payment coverage
# headline: ROUND(100.0 * cov.bookings_with_payment / b.bookings, 2)
# cov.bookings_with_payment = COUNT(DISTINCT booking_sk) FROM fact_payment
# 637 / 1000 = 63.70%
print(f"\nPayment coverage: headline={headline['payment_coverage_pct']}%, measured={round(100.0 * 637 / 1000, 2)}%")

# 6. Bookings per flight
# headline: ROUND(1.0 * b.bookings / NULLIF(f.flights, 0), 3)
# b.bookings = 1000, f.flights = 1003
print(f"\nBookings per flight: headline={headline['bookings_per_flight']}, measured={round(1000 / 1003, 3)}")

# 7. DQ score
# Let's check dq_score table:
dq_score = con.execute("SELECT * FROM dq_score").df()
print("\nDQ score table:")
print(dq_score)

con.close()
