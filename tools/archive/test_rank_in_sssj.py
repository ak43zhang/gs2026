import sys
sys.path.insert(0, 'src')
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()
client = redis_util._get_redis_client()

date = '20260403'

# 1. 获取上攻排行代码
rank_key = f'rank:bond:code_{date}'
rank_data = client.zrevrange(rank_key, 0, -1, withscores=False)
rank_codes = set()
for code in rank_data:
    code_str = code.decode('utf-8') if isinstance(code, bytes) else code
    rank_codes.add(code_str)

print(f"上攻排行代码数量: {len(rank_codes)}")
print(f"上攻排行代码: {sorted(rank_codes)}")

# 2. 获取实时数据代码
ts_key = f'monitor_zq_sssj_{date}:timestamps'
timestamps = client.lrange(ts_key, 0, 0)
if timestamps:
    latest_ts = timestamps[0].decode('utf-8') if isinstance(timestamps[0], bytes) else timestamps[0]
    sssj_key = f'monitor_zq_sssj_{date}:{latest_ts}'
    df = redis_util.load_dataframe_by_key(sssj_key, use_compression=False)
    if df is not None and not df.empty:
        sssj_codes = set(df['bond_code'].astype(str).tolist())
        print(f"\n实时数据代码数量: {len(sssj_codes)}")

        # 检查交集
        common = rank_codes & sssj_codes
        print(f"\n共同代码数量: {len(common)}")
        print(f"共同代码: {sorted(common)}")

        # 检查上攻排行独有的代码
        rank_only = rank_codes - sssj_codes
        print(f"\n上攻排行独有代码: {sorted(rank_only)}")

        # 检查实时数据独有的代码
        sssj_only = sssj_codes - rank_codes
        print(f"实时数据独有代码数量: {len(sssj_only)}")
