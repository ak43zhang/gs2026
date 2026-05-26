import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

# 检查 Redis 中缓存的数据结构
sssj_table = "monitor_zq_sssj_20260518"
redis_key = f"{sssj_table}:15:00:00"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
if df is not None:
    print(f"Columns: {list(df.columns)}")
    print(f"Shape: {df.shape}")
    print(df.head(3))
else:
    print("No data in Redis for this key")
    
# 尝试其他时间格式
for ts in ["15:00:00", "14:59:57", "14:59:55"]:
    key = f"{sssj_table}:{ts}"
    df = redis_util.load_dataframe_by_key(key, use_compression=False)
    if df is not None:
        print(f"\nFound data at {ts}, columns: {list(df.columns)}")
        break
