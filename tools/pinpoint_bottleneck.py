"""Pinpoint exact bottleneck in _get_change_pct_and_main_net_batch"""
import sys, time
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from gs2026.utils import redis_util
try:
    redis_util.init_redis()
except:
    pass

date = '20260518'
sssj_table = f"monitor_gp_sssj_{date}"

# Get latest time
client = redis_util._get_redis_client()
ts_key = f"{sssj_table}:timestamps"
latest_ts = client.lindex(ts_key, 0)
time_str = latest_ts.decode('utf-8') if latest_ts else None
print(f"Latest time: {time_str}")

# Load DataFrame
redis_key = f"{sssj_table}:{time_str}"
t0 = time.time()
df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
t1 = time.time()
print(f"Load DataFrame: {(t1-t0)*1000:.0f}ms ({len(df)} rows, {len(df.columns)} cols)")
print(f"Columns: {list(df.columns)[:15]}...")
print(f"Has cumulative_main_net: {'cumulative_main_net' in df.columns}")
print(f"Has main_net_amount: {'main_net_amount' in df.columns}")
print(f"Has change_pct: {'change_pct' in df.columns}")

# Simulate iterrows (the suspected bottleneck)
code_col = 'stock_code' if 'stock_code' in df.columns else 'code'

t2 = time.time()
change_pct_map = {}
for _, row in df.iterrows():
    code = str(row[code_col]).zfill(6)
    if row.get('change_pct') is not None:
        change_pct_map[code] = float(row['change_pct'])
t3 = time.time()
print(f"\niterrows (change_pct, {len(df)} rows): {(t3-t2)*1000:.0f}ms")

t4 = time.time()
main_net_map = {}
for _, row in df.iterrows():
    code = str(row[code_col]).zfill(6)
    if pd.notna(row.get('cumulative_main_net')) and row.get('cumulative_main_net') != 0:
        main_net_map[code] = float(row['cumulative_main_net'])
t5 = time.time()
print(f"iterrows (main_net, {len(df)} rows): {(t5-t4)*1000:.0f}ms")

# Vectorized alternative
t6 = time.time()
df[code_col] = df[code_col].astype(str).str.zfill(6)
change_pct_map2 = df.set_index(code_col)['change_pct'].dropna().to_dict()
t7 = time.time()
print(f"\nvectorized (change_pct): {(t7-t6)*1000:.0f}ms")

if 'cumulative_main_net' in df.columns:
    t8 = time.time()
    main_net_map2 = df.set_index(code_col)['cumulative_main_net'].fillna(0).to_dict()
    t9 = time.time()
    print(f"vectorized (main_net): {(t9-t8)*1000:.0f}ms")

# Filter first, then process
stock_codes_sample = list(change_pct_map.keys())[:60]
t10 = time.time()
df_filtered = df[df[code_col].isin(stock_codes_sample)]
result = df_filtered.set_index(code_col)[['change_pct', 'cumulative_main_net']].to_dict('index')
t11 = time.time()
print(f"\nfilter+dict (60 rows from {len(df)}): {(t11-t10)*1000:.0f}ms")
