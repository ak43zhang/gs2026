import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
import pandas as pd
import json

# 初始化 Redis
redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

# 检查 10:29:06 的数据
sssj_table = "monitor_zq_sssj_20260518"
redis_key = f"{sssj_table}:10:29:06"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
if df is not None:
    print(f"✓ Found data at 10:29:06")
    print(f"Columns: {list(df.columns)}")
    print(f"Shape: {df.shape}")
    print("\nSample data (first 3 rows):")
    print(df[['bond_code', 'bond_name', 'price', 'change_pct']].head(3) if 'price' in df.columns else df.head(3))
else:
    print(f"✗ No data found at 10:29:06")
    
# 尝试查找其他时间
print("\n--- Checking available timestamps ---")
client = redis_util._get_redis_client()
if client:
    ts_key = f"{sssj_table}:timestamps"
    timestamps = client.lrange(ts_key, 0, 10)
    if timestamps:
        for ts in timestamps:
            ts_str = ts.decode('utf-8') if isinstance(ts, bytes) else ts
            print(f"  {ts_str}")
            # 检查这个时间点的数据
            key = f"{sssj_table}:{ts_str}"
            df = redis_util.load_dataframe_by_key(key, use_compression=False)
            if df is not None:
                cols = list(df.columns)
                has_price = 'price' in cols
                print(f"    Columns: {cols}")
                print(f"    Has price: {has_price}")
    else:
        print("  No timestamps found")
