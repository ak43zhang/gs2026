#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

date = '20260414'

# 检查所有相关key
pattern = f"monitor_zq_sssj_{date}*"
keys = client.keys(pattern)
print(f"找到 {len(keys)} 个key:")
for key in sorted(keys):
    key_type = client.type(key)
    if key_type == 'zset':
        count = client.zcard(key)
        print(f"  {key} (zset, {count} 条)")
    elif key_type == 'list':
        count = client.llen(key)
        print(f"  {key} (list, {count} 条)")
    elif key_type == 'hash':
        count = client.hlen(key)
        print(f"  {key} (hash, {count} 条)")
    else:
        print(f"  {key} ({key_type})")
