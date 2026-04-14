#!/usr/bin/env python3
"""清除领域分析Redis缓存"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util, config_util

# 初始化Redis
config_util.load_config()
redis_util.init_redis()

client = redis_util._get_redis_client()

# 查找所有领域分析相关的key
patterns = [
    'domain:timeline:*',
    'domain:type:*',
    'domain:area:*',
    'domain:detail:*'
]

total_deleted = 0
for pattern in patterns:
    keys = client.keys(pattern)
    if keys:
        for key in keys:
            client.delete(key)
        total_deleted += len(keys)
        print(f"Deleted {len(keys)} keys for pattern: {pattern}")

print(f"\nTotal deleted: {total_deleted} keys")
