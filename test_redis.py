#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

# 获取那条数据的详情
content_hash = '31b5c320fb09dcc710f64b7f63ae1514'
detail = client.hgetall(f'domain:detail:{content_hash}')
if detail:
    print('Redis中的数据:')
    print(f"  news_size: {detail.get('news_size', 'N/A')}")
    print(f"  composite_score: {detail.get('composite_score', 'N/A')}")
    title = detail.get('key_event', 'N/A')
    print(f"  key_event: {title[:50]}...")
else:
    print('Redis中没有该数据')
