import sys
sys.path.insert(0, 'src')
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()
client = redis_util._get_redis_client()

date = '20260403'

# 1. 获取时间戳列表
ts_key = f'monitor_zq_sssj_{date}:timestamps'
timestamps = client.lrange(ts_key, 0, 5)
print(f"时间戳列表（前6个）: {[t.decode('utf-8') if isinstance(t, bytes) else t for t in timestamps]}")

# 2. 获取最新时间戳
latest_ts = client.lindex(ts_key, 0)
if latest_ts:
    latest_ts_str = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
    print(f"\n最新时间戳: {latest_ts_str}")

    # 3. 获取该时间的数据
    sssj_key = f'monitor_zq_sssj_{date}:{latest_ts_str}'
    df = redis_util.load_dataframe_by_key(sssj_key, use_compression=False)
    if df is not None and not df.empty:
        print(f"数据行数: {len(df)}")
        print(f"数据列: {df.columns.tolist()}")
        print(f"\n前3行:")
        print(df.head(3).to_string())

        # 4. 检查特定代码
        test_code = '123054'
        match = df[df['bond_code'].astype(str) == test_code]
        if not match.empty:
            print(f"\n找到代码 {test_code}:")
            print(match.to_string())
        else:
            print(f"\n未找到代码 {test_code}")
            print(f"bond_code类型: {df['bond_code'].dtype}")
            print(f"bond_code示例: {df['bond_code'].head(5).tolist()}")
