import pandas as pd
import numpy as np
import datetime

# Read raw excel directly
excel_path = "data/raw/UseCase_Airlines.xlsx"
xls = pd.ExcelFile(excel_path)
print("Sheet names:", xls.sheet_names)

flights = pd.read_excel(xls, "flights")
bookings = pd.read_excel(xls, "bookings")
payments = pd.read_excel(xls, "payments")
passengers = pd.read_excel(xls, "passengers")

print(f"flights shape: {flights.shape}")
print(f"bookings shape: {bookings.shape}")
print(f"payments shape: {payments.shape}")
print(f"passengers shape: {passengers.shape}")

# FLIGHTS
print("\n--- FLIGHTS ---")
print("airline nulls:", flights["airline"].isna().sum())
print("airline == 'UNKNOWN':", (flights["airline"] == "UNKNOWN").sum())
print("airline value counts:\n", flights["airline"].value_counts(dropna=False))

unique_flight_ids = flights["flight_id"].nunique()
print("unique flight_id:", unique_flight_ids)
dup_flight_mask = flights.duplicated(subset=["flight_id"], keep=False)
dup_flight_ids = flights.loc[dup_flight_mask, "flight_id"].unique()
print(f"duplicated flight_ids count: {len(dup_flight_ids)}, total rows: {dup_flight_mask.sum()}")
print("duplicated flight_ids:", dup_flight_ids)

# Check the 16 duplicate ids: 15 byte-identical pairs, 1 (6F250) conflicts
conflict_ids = []
identical_ids = []
for fid in dup_flight_ids:
    sub = flights[flights["flight_id"] == fid]
    if len(sub.drop_duplicates()) == 1:
        identical_ids.append(fid)
    else:
        conflict_ids.append(fid)
print(f"identical duplicate id pairs count: {len(identical_ids)}")
print(f"conflicting duplicate id count: {len(conflict_ids)}, which are: {conflict_ids}")
if conflict_ids:
    print(flights[flights["flight_id"].isin(conflict_ids)])

malformed_fids = flights[~flights["flight_id"].astype(str).str.match(r"^[A-Z0-9]{2}\d{3}$")]
print("malformed flight_ids count:", len(malformed_fids))

cities = set(flights["source"]).union(set(flights["destination"]))
print("cities count:", len(cities), cities)
routes = flights[["source", "destination"]].drop_duplicates()
print("routes count:", len(routes))
self_routes = flights[flights["source"] == flights["destination"]]
print("self routes count:", len(self_routes))

dep_min = flights["departure_time"].min()
dep_max = flights["departure_time"].max()
print(f"departure_time min: {dep_min} .. max: {dep_max}")

# midnight cross
# Note: check if departure_time and arrival_time dates differ or arrival_time < departure_time or date cross
flights["dep_dt"] = pd.to_datetime(flights["departure_time"])
flights["arr_dt"] = pd.to_datetime(flights["arrival_time"])
# Did dates cross midnight?
cross_midnight = (flights["arr_dt"].dt.date > flights["dep_dt"].dt.date)
print("cross midnight (arr date > dep date):", cross_midnight.sum())

# duration column types
print("duration types:", flights["duration"].map(type).value_counts())
# check datetime.datetime(1899, 12, 29, 5, 0)
print("duration non-time types:", [x for x in flights["duration"] if not isinstance(x, datetime.time)])

# arrival < departure
arr_lt_dep = flights[flights["arr_dt"] < flights["dep_dt"]]
print("arrival < departure count:", len(arr_lt_dep))
if len(arr_lt_dep) > 0:
    for idx, row in arr_lt_dep.iterrows():
        delta_min = (row["arr_dt"] - row["dep_dt"]).total_seconds() / 60
        print(f"row {row['flight_id']}: arr={row['arr_dt']}, dep={row['dep_dt']}, delta_min={delta_min}, raw_duration={row['duration']}")
        corr_arr = row["arr_dt"] + pd.Timedelta(days=1)
        corr_delta = (corr_arr - row["dep_dt"]).total_seconds() / 60
        print(f"corrected delta: {corr_delta} min")

micro_0 = flights[flights["dep_dt"].dt.microsecond == 0]["flight_id"].tolist()
# wait, microsecond == 0 for which column? or departure_time or arrival_time?
# Let's check microsecond == 0 in departure_time or arrival_time or both or duration:
print("dep microsecond == 0:", flights[flights["dep_dt"].dt.microsecond == 0]["flight_id"].tolist())
print("arr microsecond == 0:", flights[flights["arr_dt"].dt.microsecond == 0]["flight_id"].tolist())

# Corrected durations min and max:
# If arr < dep: arr + 1 day
arr_corrected = flights["arr_dt"].copy()
arr_corrected[flights["arr_dt"] < flights["dep_dt"]] += pd.Timedelta(days=1)
durations_corrected = (arr_corrected - flights["dep_dt"]).dt.total_seconds() / 60
print(f"corrected durations: min {durations_corrected.min()}, max {durations_corrected.max()}")

# departures in hours 22,23,0,1,2,3,4
dep_hours_night = flights["dep_dt"].dt.hour.isin([22, 23, 0, 1, 2, 3, 4]).sum()
print("departures in hours 22,23,0,1,2,3,4:", dep_hours_night)

# BOOKINGS
print("\n--- BOOKINGS ---")
print("status counts:\n", bookings["status"].value_counts(dropna=False))
print("status nulls:", bookings["status"].isna().sum())
print("status == 'INVALID':", (bookings["status"] == "INVALID").sum())
print("booking_id unique:", bookings["booking_id"].nunique(), "total rows:", len(bookings))
print("duplicate rows in bookings:", bookings.duplicated().sum())

bookings["bdate"] = pd.to_datetime(bookings["booking_date"])
print("booking_date min..max:", bookings["bdate"].min(), "..", bookings["bdate"].max())
print("distinct booking dates:", bookings["bdate"].dt.date.nunique())

orphan_fids = set(bookings["flight_id"]) - set(flights["flight_id"])
orphan_pids = set(bookings["passenger_id"]) - set(passengers["passenger_id"])
print(f"orphan flight_id: {len(orphan_fids)}, orphan passenger_id: {len(orphan_pids)}")

b_dup_fids = bookings[bookings["flight_id"].isin(dup_flight_ids)]
print(f"bookings referencing duplicated flight_ids: {len(b_dup_fids)}")
b_6F250 = bookings[bookings["flight_id"] == "6F250"]
print(f"bookings referencing 6F250: {len(b_6F250)}")

valid_passports = bookings["passport_number"].astype(str).str.match(r"^[A-Z]\d{7}$").sum()
print(f"passport matches ^[A-Z]\\d{{7}}$: {valid_passports}/{len(bookings)}")

dup_seat_pairs = bookings.duplicated(subset=["flight_id", "seat_number"]).sum()
print(f"duplicate (flight_id, seat_number) pairs: {dup_seat_pairs}")

# PAYMENTS
print("\n--- PAYMENTS ---")
print("amount types:\n", payments["amount"].map(lambda x: type(x).__name__).value_counts())
str_amounts = payments[payments["amount"].map(lambda x: isinstance(x, str))]
print("string amounts unique:", str_amounts["amount"].unique())
print("amount nulls:", payments["amount"].isna().sum())

# valid amounts: numeric (float or int)
num_amounts = pd.to_numeric(payments["amount"], errors="coerce")
valid_amounts = num_amounts.dropna()
print(f"valid amounts count: {len(valid_amounts)}")
print(f"sum of valid amounts: {valid_amounts.sum():.2f}")
print(f"min valid amount: {valid_amounts.min():.2f}, max: {valid_amounts.max():.2f}")

distinct_bids_in_pay = payments["booking_id"].nunique()
print(f"distinct booking_ids in payments: {distinct_bids_in_pay}")
pay_per_b = payments.groupby("booking_id").size().value_counts().sort_index()
print("payments-per-booking histogram:\n", pay_per_b)

bids_no_pay = set(bookings["booking_id"]) - set(payments["booking_id"])
print(f"bookings with no payment: {len(bids_no_pay)}")

# payments referencing cancelled bookings
pay_b_merged = payments.merge(bookings[["booking_id", "status"]], on="booking_id", how="left")
cancelled_pays = (pay_b_merged["status"] == "CANCELLED").sum()
print(f"payments referencing CANCELLED bookings: {cancelled_pays}")

print("payment methods:\n", payments["payment_method"].value_counts(dropna=False))

# confirmed-only revenue
confirmed_bids = set(bookings[bookings["status"] == "CONFIRMED"]["booking_id"])
confirmed_pays = payments[payments["booking_id"].isin(confirmed_bids)]
confirmed_rev = pd.to_numeric(confirmed_pays["amount"], errors="coerce").sum()
print(f"confirmed-only revenue: {confirmed_rev:.2f}")

# PASSENGERS
print("\n--- PASSENGERS ---")
print("passengers shape:", passengers.shape)
print("unique passenger_id:", passengers["passenger_id"].nunique())
print("byte-identical duplicate rows:", passengers.duplicated().sum())

dup_pid_mask = passengers.duplicated(subset=["passenger_id"], keep=False)
dup_pids = passengers.loc[dup_pid_mask, "passenger_id"].unique()
print(f"duplicated passenger ids: {len(dup_pids)}")
# histogram of group sizes
p_group_sizes = passengers[dup_pid_mask].groupby("passenger_id").size().value_counts()
print("duplicate group sizes:\n", p_group_sizes)

# check variance within duplicate groups:
cols_to_check = ["age", "gender", "first_name", "last_name", "email", "phone", "aadhaar_id", "date_of_birth"]
varies_count = {c: 0 for c in cols_to_check}
for pid in dup_pids:
    sub = passengers[passengers["passenger_id"] == pid]
    for c in cols_to_check:
        if sub[c].nunique(dropna=False) > 1:
            varies_count[c] += 1
print("variance within duplicate groups (out of 36):", varies_count)

print("last_name nulls:", passengers["last_name"].isna().sum())
print("age min..max:", passengers["age"].min(), "..", passengers["age"].max())
print("under 18 count:", (passengers["age"] < 18).sum())
print("gender values:\n", passengers["gender"].value_counts(dropna=False))

# age vs date_of_birth
# reference date or check age against dob
passengers["dob_dt"] = pd.to_datetime(passengers["date_of_birth"])
# Let's see how age vs dob is computed (e.g. as of 2026 or departure date or booking date):
# Let's check difference
ref_date = pd.Timestamp("2026-04-17")
calc_age = (ref_date - passengers["dob_dt"]).dt.days // 365.25
print("sample age vs dob calc difference:", (passengers["age"] - (ref_date.year - passengers["dob_dt"].dt.year)).value_counts().head(5))

# aadhaar_id digit lengths
# Note: aadhaar_id may be numeric or string in excel
aadhaar_lens = passengers["aadhaar_id"].dropna().astype(str).str.replace(r"\.0$", "", regex=True).str.len().value_counts()
print("aadhaar digit lengths (from str without decimal):\n", aadhaar_lens)

pids_no_booking = set(passengers["passenger_id"]) - set(bookings["passenger_id"])
print("passengers with no booking:", len(pids_no_booking))

# FAN-OUT
print("\n--- FAN-OUT ---")
# bookings ⋈ flights
b_join_f = bookings.merge(flights, on="flight_id")
print("bookings ⋈ flights rows:", len(b_join_f))

# bookings ⋈ payments
b_join_p = bookings.merge(payments, on="booking_id")
print("bookings ⋈ payments rows:", len(b_join_p))

# three-way
three_way = bookings.merge(flights, on="flight_id").merge(payments, on="booking_id")
print("three-way merge rows:", len(three_way))

naive_sum = pd.to_numeric(three_way["amount"], errors="coerce").sum()
true_sum = valid_amounts.sum()
delta = naive_sum - true_sum
print(f"naive three-way SUM(amount): {naive_sum:.2f} vs true {true_sum:.2f} ; delta {delta:.2f}")
