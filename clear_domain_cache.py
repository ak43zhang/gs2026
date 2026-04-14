#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

# 清除所有领域分析相关的缓存
keys = client.keys('domain:*')
print(f'找到 {len(keys)} 个领域分析缓存key')

if keys:
    for key in keys[:10]:
        print(f'  删除: {key}')
    client.delete(*keys)
    print(f'已清除 {len(keys)} 个缓存key')
else:
    print('没有领域分析缓存')
