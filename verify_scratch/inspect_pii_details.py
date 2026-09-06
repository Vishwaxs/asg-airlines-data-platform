import pandas as pd
import json

print("--- Inspecting dim_passenger.csv ---")
dp = pd.read_csv("data/gold/dim_passenger.csv")
print(dp[["masked_email", "masked_phone", "masked_name"]].head(10))

print("\n--- Inspecting passenger_survivorship.csv ---")
ps = pd.read_csv("reports/passenger_survivorship.csv")
print(ps.head(10))

print("\n--- Inspecting notebooks/asg_airlines_walkthrough.ipynb for 7345678901 ---")
with open("notebooks/asg_airlines_walkthrough.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

for idx, cell in enumerate(nb["cells"]):
    src = "".join(cell.get("source", []))
    if "7345678901" in src:
        print(f"Cell {idx} ({cell['cell_type']}) contains 7345678901:")
        print(src[:300])
    for out in cell.get("outputs", []):
        out_text = str(out)
        if "7345678901" in out_text:
            print(f"Cell {idx} output contains 7345678901:")
            print(out_text[:300])
