#!/usr/bin/env python3
"""测试行业交叉选股"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 重新加载缓存
stock_picker_service.load_memory_cache()

print('=== 测试电力行业 ===')
selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    for stock in group['stocks'][:5]:
        print(f"    {stock['stock_code']} {stock['stock_name']}")

print()
print('=== 测试电子化学品行业 ===')
selected_tags = [
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    for stock in group['stocks'][:5]:
        print(f"    {stock['stock_code']} {stock['stock_name']}")

print()
print('=== 测试电力 + 电子化学品（无交集） ===')
selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'},
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")

print()
print('=== 测试有交集的行业组合 ===')
# 查找有交集的行业
from collections import defaultdict
industry_counts = defaultdict(int)
for code, data in stock_picker_service._stock_cache.items():
    for ind in data.get('industries', set()):
        industry_counts[ind] += 1

print(f"行业数量: {len(industry_counts)}")
print("前10个行业:")
for ind, count in sorted(industry_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {ind}: {count} 只股票")
