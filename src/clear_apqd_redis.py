"""清除今天 apqd 的 Redis 缓存，让 API 回退到 MySQL（含 phase 字段）"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.utils import redis_util, config_util

redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)

client = redis_util._get_redis_client()

DATE = '20260527'
patterns = [
    f'monitor_gp_apqd_{DATE}:*',
    f'monitor_zq_apqd_{DATE}:*',
    f'monitor_gp_apqd_{DATE}',
    f'monitor_zq_apqd_{DATE}',
]

total = 0
for pattern in patterns:
    keys = list(client.scan_iter(match=pattern, count=1000))
    if keys:
        client.delete(*keys)
        total += len(keys)
        print(f"  Deleted {len(keys)} keys matching {pattern}")

# Also check sorted set keys
for prefix in [f'monitor_gp_apqd_{DATE}', f'monitor_zq_apqd_{DATE}']:
    if client.exists(prefix):
        client.delete(prefix)
        total += 1
        print(f"  Deleted sorted set key: {prefix}")

print(f"\nTotal deleted: {total} Redis keys")
