#!/usr/bin/env python3
"""测试智能选股功能"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 测试拼音搜索
print('=== 测试拼音搜索 ===')
results = stock_picker_service.search_tags('电力')
print(f'搜索 电力: {len(results)} 条结果')
for r in results[:5]:
    print(f"  {r['name']} ({r['type']})")

print()
results = stock_picker_service.search_tags('电子化学品')
print(f'搜索 电子化学品: {len(results)} 条结果')
for r in results[:5]:
    print(f"  {r['name']} ({r['type']})")

# 测试交叉查询
print()
print('=== 测试交叉查询 ===')
selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'},
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    for stock in group['stocks'][:3]:
        print(f"    {stock['stock_code']} {stock['stock_name']} | {stock['matched_tags_display']}")
