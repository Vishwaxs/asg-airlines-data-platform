import pandas as pd

excel_path = "data/raw/UseCase_Airlines.xlsx"
xls = pd.ExcelFile(excel_path)
flights = pd.read_excel(xls, "flights")
bookings = pd.read_excel(xls, "bookings")
payments = pd.read_excel(xls, "payments")
passengers = pd.read_excel(xls, "passengers")

# LEFT JOINS from bookings:
b_left_f = bookings.merge(flights, on="flight_id", how="left")
print("bookings LEFT JOIN flights:", len(b_left_f))

b_left_p = bookings.merge(payments, on="booking_id", how="left")
print("bookings LEFT JOIN payments:", len(b_left_p))

b_left_f_left_p = bookings.merge(flights, on="flight_id", how="left").merge(payments, on="booking_id", how="left")
print("bookings LEFT JOIN flights LEFT JOIN payments:", len(b_left_f_left_p))

naive_sum = pd.to_numeric(b_left_f_left_p["amount"], errors="coerce").sum()
print("naive sum on left join:", naive_sum)

# Now check: flights with no matching booking
f_no_b = set(flights["flight_id"]) - set(bookings["flight_id"])
print("flights with no matching booking:", len(f_no_b))

# passengers with no booking:
# Check passengers left join bookings:
p_left_b = passengers.merge(bookings[["booking_id", "passenger_id"]], on="passenger_id", how="left")
print("passengers LEFT JOIN bookings total rows:", len(p_left_b))
print("passengers LEFT JOIN bookings where booking_id is null (row count):", p_left_b["booking_id"].isna().sum())
print("passengers LEFT JOIN bookings where booking_id is null (unique passenger_id):", p_left_b[p_left_b["booking_id"].isna()]["passenger_id"].nunique())

# Wait! Look at 1039 - 657 = 382!
# Let's check: 1039 total rows in passengers.
# How many passenger rows in passengers match a booking?
# If p_left_b has 382 rows with booking_id null!
# Let's see!
