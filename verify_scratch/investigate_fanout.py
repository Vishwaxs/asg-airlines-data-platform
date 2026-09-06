import pandas as pd

excel_path = "data/raw/UseCase_Airlines.xlsx"
xls = pd.ExcelFile(excel_path)
flights = pd.read_excel(xls, "flights")
bookings = pd.read_excel(xls, "bookings")
payments = pd.read_excel(xls, "payments")
passengers = pd.read_excel(xls, "passengers")

print("--- Investigating 1363, 1404, and 382 ---")
# If passengers (1039 rows) is involved?
# passengers has 1039 rows.
# bookings join passengers on passenger_id:
bp = bookings.merge(passengers, on="passenger_id")
print("bookings merge passengers:", len(bp))

# bp merge payments on booking_id:
bpp = bp.merge(payments, on="booking_id")
print("bookings merge passengers merge payments:", len(bpp))

# bookings merge flights (1032 rows) merge passengers?
bfp = bookings.merge(flights, on="flight_id").merge(passengers, on="passenger_id")
print("bookings merge flights merge passengers:", len(bfp))

# three way: flights * bookings * payments * passengers?
# What about flights * bookings * payments * passengers?
bfpp = bookings.merge(flights, on="flight_id").merge(payments, on="booking_id").merge(passengers, on="passenger_id")
print("bfpp:", len(bfpp))

# What if passengers merge bookings (right join or left join)?
# How can bookings join payments be 1363?
# Could it be passengers join bookings (where duplicate passengers exist)?
# 1000 bookings join passengers (1039 rows, 36 duplicate passenger_ids):
# Let's check:
print("bookings merge passengers on passenger_id:", len(bookings.merge(passengers, on="passenger_id")))
# If we join passengers (with duplicates) and payments (with multiple payments per booking):
p_b_pay = passengers.merge(bookings, on="passenger_id").merge(payments, on="booking_id")
print("passengers merge bookings merge payments:", len(p_b_pay))

# What about:
f_b_pay = flights.merge(bookings, on="flight_id").merge(payments, on="booking_id")
print("flights merge bookings merge payments:", len(f_b_pay))
print("naive sum f_b_pay:", pd.to_numeric(f_b_pay["amount"], errors="coerce").sum())

# Wait! Look at naive_sum:
# In check_details.py: naive sum = 7593758.92, valid_amt_sum = 7385142.98, delta = 208615.94!
# Wait! In check_details.py:
# naive_sum was EXACTLY 7593758.92!
# And delta was EXACTLY 208615.94!
# But len(b_f_p) was 1028 in check_details.py!
# Wait! What was 1404 then?
# Could 1404 be when passengers is also joined?
# Let's check:
all_4 = flights.merge(bookings, on="flight_id").merge(passengers, on="passenger_id").merge(payments, on="booking_id")
print("all 4 merged:", len(all_4))
print("naive sum all 4:", pd.to_numeric(all_4["amount"], errors="coerce").sum())

# What about 1363?
# What table has 1363?
for name1, df1, key1 in [("b", bookings, "passenger_id"), ("f", flights, "flight_id"), ("pay", payments, "booking_id")]:
    for name2, df2, key2 in [("p", passengers, "passenger_id"), ("pay", payments, "booking_id")]:
        pass

# Let's test combinations of merges:
m1 = passengers.merge(bookings, on="passenger_id").merge(payments, on="booking_id")
print("passengers * bookings * payments:", len(m1)) # Is this 1363 or 1060?

# And where does 382 passengers with no booking come from?
# Let's check:
# 1000 - 382 = 618.
# Is there any subset of bookings with 618 distinct passengers?
print("distinct passenger_id in bookings with status != CANCELLED:", bookings[bookings["status"] != "CANCELLED"]["passenger_id"].nunique())
print("distinct passenger_id in bookings with status in (CONFIRMED, PENDING):", bookings[bookings["status"].isin(["CONFIRMED", "PENDING"])]["passenger_id"].nunique())
print("distinct passenger_id in bookings with payment:", bookings[bookings["booking_id"].isin(payments["booking_id"])]["passenger_id"].nunique())
# What if 1039 - 382 = 657?
# Or 1000 unique passengers vs what?
# What about passengers in raw excel:
print("passengers without booking if we check something else?")
