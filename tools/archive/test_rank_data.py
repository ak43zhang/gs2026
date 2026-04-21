import sys
sys.path.insert(0, 'src')
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()
client = redis_util._get_redis_client()

date = '20260403'

# 1. 获取上攻排行的代码（来自rank）
rank_key = f'rank:bond:code_{date}'
rank_data = client.zrevrange(rank_key, 0, 4, withscores=True)
print("=== 上攻排行代码（来自rank）===")
for code, score in rank_data:
    code_str = code.decode('utf-8') if isinstance(code, bytes) else code
    print(f"  {code_str}: {int(score)}")

# 2. 获取实时数据的代码（来自sssj）
print("\n=== 实时数据代码（来自sssj）===")
ts_key = f'monitor_zq_sssj_{date}:timestamps'
timestamps = client.lrange(ts_key, 0, 0)
if timestamps:
    latest_ts = timestamps[0].decode('utf-8') if isinstance(timestamps[0], bytes) else timestamps[0]
    sssj_key = f'monitor_zq_sssj_{date}:{latest_ts}'
    df = redis_util.load_dataframe_by_key(sssj_key, use_compression=False)
    if df is not None and not df.empty:
        print(f"前5个代码: {df['bond_code'].head(5).tolist()}")
        print(f"代码类型: {df['bond_code'].dtype}")
