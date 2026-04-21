import sys
sys.path.insert(0, 'src')
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()
client = redis_util._get_redis_client()

date = '20260403'

# 获取时间戳列表
ts_key = f'monitor_zq_sssj_{date}:timestamps'
timestamps = client.lrange(ts_key, 0, 5)
print(f'时间戳列表: {[t.decode("utf-8") if isinstance(t, bytes) else t for t in timestamps]}')

# 获取最新时间的数据
if timestamps:
    latest_ts = timestamps[0].decode('utf-8') if isinstance(timestamps[0], bytes) else timestamps[0]
    redis_key = f'monitor_zq_sssj_{date}:{latest_ts}'
    print(f'\n查询key: {redis_key}')
    
    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    if df is not None and not df.empty:
        print(f'数据shape: {df.shape}')
        print(f'列名: {df.columns.tolist()}')
        print(f'\n前5行:')
        print(df.head(5).to_string())
        print(f'\nbond_code列类型: {df["bond_code"].dtype}')
        print(f'bond_code示例: {df["bond_code"].head(5).tolist()}')
    else:
        print('数据为空')
else:
    print('没有时间戳数据')
