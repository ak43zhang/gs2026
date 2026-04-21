#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排查股票上攻排行调用链路 - 300992债券不显示问题
"""
import json
from datetime import datetime
from gs2026.utils import redis_util, log_util
from gs2026.utils.stock_bond_mapping_cache import StockBondMappingCache, get_cache

logger = log_util.setup_logger(__file__)

print('=' * 70)
print('排查股票上攻排行调用链路 - 300992债券不显示问题')
print('=' * 70)

# 1. 检查缓存中的300992
print('\n【步骤1】检查Redis缓存中的300992')
cache = get_cache()
mapping = cache.get_mapping('300992')
print(f'缓存查询结果: {mapping}')

# 2. 检查缓存最新日期
print('\n【步骤2】检查缓存最新日期')
latest_date = cache.get_latest_date()
print(f'缓存最新日期: {latest_date}')

# 3. 检查今天的缓存key是否存在
print('\n【步骤3】检查今天的缓存key')
today = datetime.now().strftime('%Y-%m-%d')
print(f'今天日期: {today}')
mapping_key = f'stock_bond_mapping:{today}'
redis_client = redis_util._get_redis_client()
exists = redis_client.exists(mapping_key)
print(f'缓存key存在: {exists}')

# 4. 检查缓存中的300992（直接查询Redis）
print('\n【步骤4】直接查询Redis中的300992')
data = redis_client.hget(mapping_key, '300992')
print(f'直接查询结果: {data}')
if data:
    print(f'解析后: {json.loads(data)}')

# 5. 检查缓存元数据
print('\n【步骤5】检查缓存元数据')
meta_key = 'stock_bond_mapping:meta'
meta_data = redis_client.get(meta_key)
if meta_data:
    meta = json.loads(meta_data)
    print(f'缓存元数据: {json.dumps(meta, indent=2, ensure_ascii=False)}')
else:
    print('无元数据')

# 6. 测试重新生成映射数据
print('\n【步骤6】测试重新生成映射数据（不写入缓存）')
from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping
df = get_stock_bond_industry_mapping(
    min_bond_price=0.0,      # 放宽价格限制
    max_bond_price=500.0
)
print(f'生成映射总数: {len(df)}')
result = df[df['stock_code'] == '300992']
print(f'300992在映射中: {not result.empty}')
if not result.empty:
    print(f'300992映射数据:')
    print(result.to_string())

# 7. 检查缓存中的债券数量
print('\n【步骤7】检查缓存中的债券数量')
all_mapping = cache.get_all_mapping()
total = len(all_mapping)
with_bond = sum(1 for m in all_mapping.values() if m.get('bond_code') and m['bond_code'] != '-')
print(f'缓存总记录数: {total}')
print(f'有债券的记录数: {with_bond}')

print('\n' + '=' * 70)
print('排查完成')
print('=' * 70)
