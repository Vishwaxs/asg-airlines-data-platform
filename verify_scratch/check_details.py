import pandas as pd
import numpy as np

excel_path = "data/raw/UseCase_Airlines.xlsx"
xls = pd.ExcelFile(excel_path)
flights = pd.read_excel(xls, "flights")
bookings = pd.read_excel(xls, "bookings")
payments = pd.read_excel(xls, "payments")
passengers = pd.read_excel(xls, "passengers")

# Fix encoding
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 1. Midnight check
flights["dep_dt"] = pd.to_datetime(flights["departure_time"])
flights["arr_dt"] = pd.to_datetime(flights["arrival_time"])
arr_corr = flights["arr_dt"].copy()
arr_corr[flights["arr_dt"] < flights["dep_dt"]] += pd.Timedelta(days=1)
cross_midnight_raw = (flights["arr_dt"].dt.date != flights["dep_dt"].dt.date).sum()
cross_midnight_corr = (arr_corr.dt.date != flights["dep_dt"].dt.date).sum()
print(f"cross midnight raw: {cross_midnight_raw}, corrected: {cross_midnight_corr}")

# 2. Passengers duplicate groups
dup_pid_mask = passengers.duplicated(subset=["passenger_id"], keep=False)
dup_pids = passengers.loc[dup_pid_mask, "passenger_id"].unique()

# Check last_name variance with dropna=True vs dropna=False
var_dropna_true = 0
var_dropna_false = 0
for pid in dup_pids:
    sub = passengers[passengers["passenger_id"] == pid]
    if sub["last_name"].dropna().nunique() > 1:
        var_dropna_true += 1
    if sub["last_name"].nunique(dropna=False) > 1:
        var_dropna_false += 1
print(f"last_name varies (dropna=True): {var_dropna_true}, (dropna=False): {var_dropna_false}")

# Check first_name variance
fn_var_true = sum(passengers[passengers["passenger_id"] == pid]["first_name"].dropna().nunique() > 1 for pid in dup_pids)
fn_var_false = sum(passengers[passengers["passenger_id"] == pid]["first_name"].nunique(dropna=False) > 1 for pid in dup_pids)
print(f"first_name varies (dropna=True): {fn_var_true}, (dropna=False): {fn_var_false}")

# 3. Passengers with no booking
all_pids = set(passengers["passenger_id"])
booking_pids = set(bookings["passenger_id"])
print(f"Total unique passenger_ids in passengers: {len(all_pids)}")
print(f"Total unique passenger_ids in bookings: {len(booking_pids)}")
print(f"Unique passengers not in bookings: {len(all_pids - booking_pids)}")

# What if it's based on passenger rows (1039) or what?
# Or bookings with valid status?
# What if bookings with status == 'CONFIRMED' or not CANCELLED?
for status_filter in [None, "CONFIRMED", "VALID (non-invalid/non-null)", "NON-CANCELLED"]:
    if status_filter is None:
        bp = set(bookings["passenger_id"])
    elif status_filter == "CONFIRMED":
        bp = set(bookings[bookings["status"] == "CONFIRMED"]["passenger_id"])
    elif status_filter == "VALID (non-invalid/non-null)":
        bp = set(bookings[bookings["status"].isin(["CONFIRMED", "CANCELLED", "PENDING"])]["passenger_id"])
    elif status_filter == "NON-CANCELLED":
        bp = set(bookings[bookings["status"].isin(["CONFIRMED", "PENDING"])]["passenger_id"])
    print(f"Passengers not in bookings ({status_filter}): {len(all_pids - bp)}")

# Let's check how 382 is obtained:
# 1000 - 382 = 618
# 1039 - 382 = 657
# Let's check if 618 or 657 appears anywhere in bookings:
print("bookings count by status:")
print(bookings["status"].value_counts(dropna=False))

# 4. FAN-OUT
# bookings (1000) join flights (1020) on flight_id
b_f = bookings.merge(flights, on="flight_id")
print("bookings join flights count:", len(b_f))

# bookings (1000) join payments (1000) on booking_id
b_p = bookings.merge(payments, on="booking_id")
print("bookings join payments count:", len(b_p))

# three-way
b_f_p = bookings.merge(flights, on="flight_id").merge(payments, on="booking_id")
print("three-way join count:", len(b_f_p))

naive_sum = pd.to_numeric(b_f_p["amount"], errors="coerce").sum()
valid_amt_sum = pd.to_numeric(payments["amount"], errors="coerce").sum()
print(f"naive sum: {naive_sum:.2f}, valid_amt_sum: {valid_amt_sum:.2f}, delta: {naive_sum - valid_amt_sum:.2f}")

# 5. Check repo's implementation and reports
