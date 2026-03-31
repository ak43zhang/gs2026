#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from gs2026.utils import redis_util

redis_util.init_redis()
redis_client = redis_util._get_redis_client()

meta = redis_client.get('stock_bond_mapping:meta')
if meta:
    meta = json.loads(meta)
    print('缓存元数据:')
    print('  创建时间:', meta.get('created_at'))
    print('  总记录数:', meta.get('total_count'))
    print('  价格范围:', meta.get('price_range'))
    print('  债券数据日期:', meta.get('bond_daily_date'))

key = 'stock_bond_mapping:2026-03-31'
ttl = redis_client.ttl(key)
print('\n缓存key TTL:', ttl, '秒')

data = redis_client.hget(key, '300992')
if data:
    d = json.loads(data)
    print('\n300992缓存数据:')
    print('  stock_code:', d.get('stock_code'))
    print('  bond_code:', repr(d.get('bond_code')))
    print('  bond_name:', repr(d.get('bond_name')))
    print('  问题: bond_code为空字符串，说明缓存生成时未关联到债券')
