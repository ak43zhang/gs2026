import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 模拟 Flask 环境初始化 Redis
from gs2026.utils import redis_util
redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

sssj_table = "monitor_zq_sssj_20260518"
redis_key = f"{sssj_table}:10:29:06"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
if df is not None:
    print(f"Columns: {list(df.columns)}")
    print(f"Columns types: {[type(c) for c in df.columns]}")
    print(f"'price' in df.columns: {'price' in df.columns}")
    
    # 检查是否有 price 列（忽略大小写）
    price_cols = [c for c in df.columns if 'price' in str(c).lower()]
    print(f"Price-like columns: {price_cols}")
