#!/usr/bin/env python3
"""测试债券上攻排行完整调用链"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime

# 模拟请求参数
date = '20260401'
time_str = '10:25:27'
limit = 30

print('=== 测试债券上攻排行调用链 ===')
print(f'日期: {date}')
print(f'时间: {time_str}')
print()

# 1. 测试 data_service.get_bond_ranking
print('1. 测试 data_service.get_bond_ranking:')
from gs2026.dashboard.services.data_service import DataService
data_service = DataService()
data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=True)
print(f'   返回 {len(data)} 条数据')
if data:
    print(f'   样例: {data[0]}')
bond_codes = [item['code'] for item in data]
print(f'   债券代码: {bond_codes[:5]}...')
print()

# 2. 测试 _enrich_bond_data
print('2. 测试 _enrich_bond_data:')
from gs2026.dashboard2.routes.monitor import _enrich_bond_data, _get_bond_change_pct_batch

# 先测试 _get_bond_change_pct_batch
print('   2.1 测试 _get_bond_change_pct_batch:')
change_pct_map = _get_bond_change_pct_batch(date, time_str, bond_codes)
print(f'       返回 {len(change_pct_map)} 条涨跌幅数据')
if change_pct_map:
    items = list(change_pct_map.items())[:3]
    for code, pct in items:
        print(f'       {code}: {pct}')
else:
    print('       无涨跌幅数据!')
print()

# 再测试完整的 _enrich_bond_data
print('   2.2 测试完整的 _enrich_bond_data:')
enriched_data = _enrich_bond_data(data, date, time_str)
print(f'       返回 {len(enriched_data)} 条数据')
if enriched_data:
    sample = enriched_data[0]
    print(f'       样例: {sample}')
    has_change_pct = 'change_pct' in sample and sample['change_pct'] != '-'
    has_industry = 'industry_name' in sample and sample['industry_name'] != '-'
    print(f'       有涨跌幅: {has_change_pct}')
    print(f'       有行业: {has_industry}')
print()

print('=== 测试完成 ===')
