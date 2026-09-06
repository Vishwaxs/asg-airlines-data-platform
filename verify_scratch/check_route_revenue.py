import sys
sys.path.insert(0, ".")
import duckdb
import pandas as pd

con = duckdb.connect("warehouse/asg_airlines.duckdb", read_only=True)

# Check bookings on 6F250
b_6f250 = con.execute("SELECT * FROM fact_booking WHERE flight_sk = -1").df()
print("Bookings on 6F250:")
print(b_6f250)

# Check payments for these bookings:
p_6f250 = con.execute("""
    SELECT p.* 
    FROM fact_payment p
    JOIN fact_booking b ON b.booking_sk = p.booking_sk
    WHERE b.flight_sk = -1
""").df()
print("\nPayments for bookings on 6F250:")
print(p_6f250)

# Check route revenue sum
v_route_rev = con.execute("SELECT SUM(revenue) as total_route_revenue FROM v_route_revenue").df()
print("\nTotal revenue in v_route_revenue:", v_route_rev["total_route_revenue"].values[0])

v_route_perf = con.execute("SELECT SUM(revenue) as total_route_revenue FROM v_route_performance").df()
print("Total revenue in v_route_performance:", v_route_perf["total_route_revenue"].values[0])

# Total revenue in v_revenue_summary:
v_rev_sum = con.execute("SELECT gross_revenue, confirmed_revenue, cancelled_revenue FROM v_revenue_summary").df()
print("v_revenue_summary:")
print(v_rev_sum)

# Total valid payments in fact_payment:
tot_fact_payment = con.execute("SELECT SUM(amount) FROM fact_payment").df()
print("Total SUM(amount) in fact_payment:", tot_fact_payment.values[0][0])

con.close()
