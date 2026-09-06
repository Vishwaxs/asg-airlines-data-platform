import sys
sys.path.insert(0, ".")
import pandas as pd
import numpy as np
import duckdb
from pathlib import Path
import re

# Part 2 — Items 1 to 9 checks
print("=== PART 2: ITEMS 1 TO 9 AUDIT ===")

# Item 1: Duration
# Check src/clean.py: lines 51-72
# Does pd.to_timedelta get called on raw duration?
# Is +1-day applied only when arrival < departure?
# Test all 125 cross-midnight rows:
excel_path = "data/raw/UseCase_Airlines.xlsx"
flights = pd.read_excel(excel_path, sheet_name="flights")
flights["dep_ts"] = pd.to_datetime(flights["departure_time"])
flights["arr_ts"] = pd.to_datetime(flights["arrival_time"])
raw_diff = (flights["arr_ts"] - flights["dep_ts"]).dt.total_seconds() / 60
print("Item 1: raw arrival < departure count:", (raw_diff < 0).sum())
# rows where arr date != dep date but arr > dep:
cross_midnight_valid = (flights["arr_ts"].dt.date != flights["dep_ts"].dt.date) & (raw_diff > 0)
print("Item 1: legitimate cross-midnight rows (arr > dep):", cross_midnight_valid.sum())
# If +1 day was applied when arr < dep:
arr_fixed = flights["arr_ts"].copy()
arr_fixed[raw_diff < 0] += pd.Timedelta(days=1)
dur_fixed = (arr_fixed - flights["dep_ts"]).dt.total_seconds() / 60
print(f"Item 1: min duration: {dur_fixed.min()}, max duration: {dur_fixed.max()}")
print("Item 1: any spurious day added to valid cross-midnight flights?", (dur_fixed > 300).sum())

# Item 2: Overnight vs red-eye
# src/clean.py lines 92-96:
# flights["is_overnight"] = flights["departure_ts"].dt.date != flights["arrival_ts"].dt.date
# flights["departure_hour"] = flights["departure_ts"].dt.hour
# flights["is_red_eye"] = (flights["departure_hour"] >= config.red_eye_start_hour) | (flights["departure_hour"] <= config.red_eye_end_hour)
# Test cases:
# 1. 23:30 -> 01:15 : overnight? Yes. red-eye? 23 is >= 22 (or whatever config is), so red-eye? Yes.
# 2. 02:00 -> 04:30 (same day) : overnight? No. red-eye? 2 is <= 4, so red-eye? Yes.
# 3. 23:50 -> 00:10 : overnight? Yes. red-eye? 23 is >= 22, so red-eye? Yes.
# What if 20:00 -> 00:30 (next day)? overnight=True, dep_hour=20 (not red_eye if red_eye is 22..4).
print("\nItem 2: Overnight vs red-eye distinctness:")
# Let's check config.py for red_eye_start_hour and red_eye_end_hour
from src.config import load_config
cfg = load_config()
print(f"Config red-eye: start={cfg.red_eye_start_hour}, end={cfg.red_eye_end_hour}")

# Item 3: Time-only parsing
# Did clean.py use .dt.time or .dt.hour to compute duration?
# Line 55: (flights["arrival_ts"] - flights["departure_ts"]).dt.total_seconds() / 60
# It uses full timestamps (pd.to_datetime)!

# Item 4: Flight dedup
# Check fact_flight in duckdb warehouse and gold/silver:
con = duckdb.connect("warehouse/asg_airlines.duckdb", read_only=True)
fact_flight = con.execute("SELECT * FROM fact_flight").df()
print("\nItem 4: fact_flight rows:", len(fact_flight))
print("fact_flight flight_sk min..max:", fact_flight["flight_sk"].min(), "..", fact_flight["flight_sk"].max())
print("fact_flight unique flight_sk:", fact_flight["flight_sk"].nunique())
# Note: includes -1 unknown row!
real_fact_flight = fact_flight[fact_flight["flight_sk"] != -1]
print("real_fact_flight rows (excluding -1):", len(real_fact_flight))
print("real_fact_flight unique flight_id:", real_fact_flight["flight_id"].nunique())
print("is 6F250 in real_fact_flight?", "6F250" in real_fact_flight["flight_id"].values)
q_flights = pd.read_csv("data/quarantine/flights.csv")
print("quarantined flights:", q_flights[["flight_id", "quarantine_reason"]].to_dict("records"))

# Item 5: Booking preservation
fact_booking = con.execute("SELECT * FROM fact_booking").df()
print("\nItem 5: fact_booking rows:", len(fact_booking))
b_6f250 = fact_booking[fact_booking["flight_sk"] == -1]
print("bookings pointing to unknown_flight_sk (-1):", len(b_6f250))
print("booking_ids for flight_sk == -1:", b_6f250["booking_id"].tolist())

# Item 6: Passenger survivorship
# Let's check the survivorship rule:
# fewest nulls, then 12-digit aadhaar, then lowest email
# Let's check reports/passenger_survivorship.csv:
surv_df = pd.read_csv("reports/passenger_survivorship.csv")
print("\nItem 6: passenger_survivorship.csv rows:", len(surv_df))
print("survivorship winners count:", surv_df["survived"].sum())
print("reasons counts:\n", surv_df[surv_df["survived"]]["reason"].value_counts())

# Test 3 duplicate groups by hand from raw:
passengers_raw = pd.read_excel(excel_path, sheet_name="passengers")
dup_ids = surv_df["passenger_id"].unique()[:3]
for pid in dup_ids:
    sub = passengers_raw[passengers_raw["passenger_id"] == pid]
    print(f"\nGroup {pid} in raw:")
    for idx, row in sub.iterrows():
        print(f"  idx {idx}: nulls={row.isna().sum()}, aadhaar_len={len(str(row['aadhaar_id']))}, email={row['email']}")
    logged = surv_df[surv_df["passenger_id"] == pid]
    winner_row = logged[logged["survived"]]
    print(f"  Winner in log: idx {winner_row['candidate_row'].values[0]}, reason: {winner_row['reason'].values[0]}")

# Item 7: Payment grain
fact_payment = con.execute("SELECT * FROM fact_payment").df()
print("\nItem 7: fact_payment rows:", len(fact_payment))
print("fact_payment valid amount sum:", fact_payment["amount"].sum())
# Check gold exports: does any wide denormalised export exist?
gold_dir = Path("data/gold")
print("Gold directory files:", [f.name for f in gold_dir.iterdir()])
for f in gold_dir.glob("*.csv"):
    df_g = pd.read_csv(f)
    if "amount" in df_g.columns:
        print(f"File {f.name} has amount: sum = {df_g['amount'].sum():.2f}")

# Item 8: "INVALID" amounts
print("\nItem 8: 'INVALID' amounts:")
print(fact_payment["amount_quality"].value_counts())
print("Null amounts count in fact_payment:", fact_payment["amount"].isna().sum())
print("Zero amounts count in fact_payment:", (fact_payment["amount"] == 0).sum())

# Item 9: Aadhaar zfill
from src.pii import passenger_surrogate_key
# Take a passenger whose aadhaar has 10 digits
p_10 = passengers_raw[passengers_raw["aadhaar_id"].astype(str).str.len() == 10].iloc[0]
raw_val = p_10["aadhaar_id"]
pepper = cfg.pepper()
sk_raw = passenger_surrogate_key(raw_val, pepper)
sk_unpadded = passenger_surrogate_key(str(raw_val), pepper) # wait, what does passenger_surrogate_key do?
# In pii.py: normalized = str(aadhaar_id).zfill(12)
# If someone didn't zfill:
from src.pii import hmac_token
token_with_zfill = hmac_token(str(raw_val).zfill(12), pepper)
token_without_zfill = hmac_token(str(raw_val), pepper)
print(f"Item 9: 10-digit aadhaar raw value: {raw_val}")
print(f"Token with zfill(12): {token_with_zfill}")
print(f"Token without zfill:  {token_without_zfill}")
print(f"Do they differ? {token_with_zfill != token_without_zfill}")

con.close()
