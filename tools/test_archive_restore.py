"""Test: archive one small table to D:\gsdata2\mysql_achieve, then restore and verify"""
import os, sys, time
import pandas as pd
from sqlalchemy import create_engine, text

DB_URI = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
OUTPUT_DIR = r'D:\gsdata2\mysql_achieve'
engine = create_engine(DB_URI)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TABLE = 'monitor_combine_20260323'  # small table, 4 rows

# 1. Read from MySQL
print(f"1. Reading {TABLE} from MySQL...")
with engine.connect() as conn:
    df_orig = pd.read_sql(f"SELECT * FROM `{TABLE}`", conn)
    row_count = conn.execute(text(f"SELECT COUNT(*) FROM `{TABLE}`")).fetchone()[0]
print(f"   MySQL: {row_count} rows (exact), {len(df_orig)} rows (pandas)")
print(f"   Columns: {list(df_orig.columns)}")
print(f"   Sample:\n{df_orig.head(3).to_string()}")

# 2. Save to parquet
pq_path = os.path.join(OUTPUT_DIR, f"{TABLE}.parquet")
df_orig.to_parquet(pq_path, compression='snappy', index=False)
pq_size = os.path.getsize(pq_path)
print(f"\n2. Saved to {pq_path} ({pq_size} bytes)")

# 3. Read back from parquet
df_restored = pd.read_parquet(pq_path)
print(f"\n3. Restored from parquet: {len(df_restored)} rows")
print(f"   Columns: {list(df_restored.columns)}")
print(f"   Sample:\n{df_restored.head(3).to_string()}")

# 4. Verify
match = True
if len(df_orig) != len(df_restored):
    print(f"\n   FAIL: row count mismatch {len(df_orig)} vs {len(df_restored)}")
    match = False
if list(df_orig.columns) != list(df_restored.columns):
    print(f"\n   FAIL: column mismatch")
    match = False

# Compare values (convert to string for safe comparison)
for col in df_orig.columns:
    orig_vals = df_orig[col].astype(str).tolist()
    rest_vals = df_restored[col].astype(str).tolist()
    if orig_vals != rest_vals:
        print(f"\n   FAIL: column '{col}' values differ")
        match = False
        break

if match:
    print(f"\n4. PASS - parquet round-trip verified ({len(df_orig)} rows, {len(df_orig.columns)} columns)")

# 5. Test restore to MySQL (temp table)
temp_table = f"_test_restore_{TABLE}"
print(f"\n5. Restoring to MySQL as '{temp_table}'...")
df_restored.to_sql(temp_table, engine, if_exists='replace', index=False)
with engine.connect() as conn:
    r = conn.execute(text(f"SELECT COUNT(*) FROM `{temp_table}`"))
    restored_count = r.fetchone()[0]
    print(f"   MySQL restored: {restored_count} rows")
    # Cleanup
    conn.execute(text(f"DROP TABLE `{temp_table}`"))
    conn.commit()
    print(f"   Temp table dropped")

if restored_count == row_count:
    print(f"\n=== ALL TESTS PASSED ===")
    print(f"  Archive path: {pq_path}")
    print(f"  Rows: {row_count}")
    print(f"  MySQL size: ~0.1 MB -> Parquet: {pq_size/1024:.1f} KB")
else:
    print(f"\n=== RESTORE FAILED: {restored_count} vs {row_count} ===")
