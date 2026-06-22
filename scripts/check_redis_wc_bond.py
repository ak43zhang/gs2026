import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.utils import redis_util, config_util
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port)
client = redis_util._get_redis_client()

import datetime
today = datetime.datetime.now().strftime('%Y%m%d')

# 检查债券
table = f'monitor_zq_top30_{today}'
ts = client.lrange(f'{table}:timestamps', 0, 3)
print(f'Bond table: {table}')
print(f'Timestamps: {[t.decode() if isinstance(t, bytes) else t for t in ts]}')

if ts:
    latest = ts[0].decode() if isinstance(ts[0], bytes) else ts[0]
    df = redis_util.load_dataframe_by_key(f'{table}:{latest}', use_compression=False)
    if df is not None:
        has_wc = 'window_count' in df.columns
        print(f'Has window_count: {has_wc}')
        if has_wc:
            print(df[['code','name','window_count']].head(5).to_string())
    else:
        print('DataFrame is None')
else:
    print('No timestamps')
