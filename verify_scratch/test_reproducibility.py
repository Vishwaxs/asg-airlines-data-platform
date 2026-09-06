import sys
import shutil
from pathlib import Path
import subprocess
import pandas as pd
import duckdb

print("=== REPRODUCIBILITY TEST ===")

backup_dir = Path("verify_scratch/backup")
backup_dir.mkdir(parents=True, exist_ok=True)

# 1. Backup existing directories
for d in ["data/bronze", "data/silver", "data/gold", "warehouse"]:
    src_p = Path(d)
    dst_p = backup_dir / d
    if dst_p.exists():
        shutil.rmtree(dst_p)
    if src_p.exists():
        shutil.copytree(src_p, dst_p)

print("Backup created.")

# 2. Delete generated data
for d in ["data/bronze", "data/silver", "data/gold", "warehouse"]:
    p = Path(d)
    if p.exists():
        shutil.rmtree(p)

print("Deleted bronze, silver, gold, warehouse.")

# 3. Run pipeline
cmd = [sys.executable, "-m", "src.pipeline"]
res = subprocess.run(cmd, capture_output=True, text=True)
print("Pipeline return code:", res.returncode)
if res.returncode != 0:
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
else:
    print("Pipeline completed successfully!")

# 4. Compare outputs
diffs = []
gold_new = Path("data/gold")
gold_old = backup_dir / "data/gold"

for f in gold_old.glob("*.csv"):
    f_new = gold_new / f.name
    if not f_new.exists():
        diffs.append(f"Missing file in new run: {f.name}")
        continue
    df_old = pd.read_csv(f)
    df_new = pd.read_csv(f_new)
    # drop _run_id if present
    cols_to_check = [c for c in df_old.columns if c != "_run_id" and not c.startswith("generated_at")]
    df_old_sub = df_old[cols_to_check]
    df_new_sub = df_new[cols_to_check]
    if not df_old_sub.equals(df_new_sub):
        diffs.append(f"Data diff in gold file: {f.name}")

# Check silver parquets
silver_new = Path("data/silver")
silver_old = backup_dir / "data/silver"
for f in silver_old.glob("*.parquet"):
    f_new = silver_new / f.name
    if not f_new.exists():
        diffs.append(f"Missing silver file: {f.name}")
        continue
    df_old = pd.read_parquet(f)
    df_new = pd.read_parquet(f_new)
    cols = [c for c in df_old.columns if c != "_run_id"]
    if not df_old[cols].equals(df_new[cols]):
        diffs.append(f"Data diff in silver parquet: {f.name}")

# Check duckdb tables
con_old = duckdb.connect(str(backup_dir / "warehouse/asg_airlines.duckdb"), read_only=True)
con_new = duckdb.connect("warehouse/asg_airlines.duckdb", read_only=True)

tables = ["dim_date", "dim_airline", "dim_route", "dim_status", "dim_passenger", "fact_flight", "fact_booking", "fact_payment"]
for t in tables:
    old_df = con_old.execute(f"SELECT * FROM {t}").df()
    new_df = con_new.execute(f"SELECT * FROM {t}").df()
    if not old_df.equals(new_df):
        diffs.append(f"Data diff in duckdb table: {t}")

con_old.close()
con_new.close()

if not diffs:
    print("ALL OUTPUTS ARE BIT-FOR-BIT IDENTICAL (apart from run_id/timestamps)!")
else:
    print("Discrepancies found:")
    for d in diffs:
        print("  -", d)
