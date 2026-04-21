#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from gs2026.utils import redis_util
from gs2026.utils.stock_bond_mapping_cache import get_cache

redis_util.init_redis()
cache = get_cache()

print('=' * 60)
print('缓存更新验证')
print('=' * 60)

print('\n1. 300992映射:')
mapping = cache.get_mapping('300992')
print('   ', mapping)

print('\n2. 缓存元数据:')
redis_client = redis_util._get_redis_client()
meta = redis_client.get('stock_bond_mapping:meta')
if meta:
    meta = json.loads(meta)
    print('   创建时间:', meta.get('created_at'))
    print('   价格范围:', meta.get('price_range'))
    print('   总记录数:', meta.get('total_count'))

print('\n3. 统计信息:')
all_mapping = cache.get_all_mapping()
total = len(all_mapping)
with_bond = sum(1 for m in all_mapping.values() if m.get('bond_code') and m['bond_code'] != '-')
print('   总股票数:', total)
print('   有债券的:', with_bond)

print('\n' + '=' * 60)
print('验证完成！请刷新前端页面 (Ctrl+F5)')
print('=' * 60)
