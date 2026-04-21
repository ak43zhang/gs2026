#!/usr/bin/env python3
"""测试有交集的行业"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 测试有交集的行业组合
print('=== 测试半导体 + 电子化学品 ===')
selected_tags = [
    {'name': '半导体', 'code': '881121', 'type': 'industry'},
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    for stock in group['stocks'][:3]:
        print(f"    {stock['stock_code']} {stock['stock_name']} | 行业:{stock['matched_industries']} | 概念:{stock['matched_concepts']}")

print()
print('=== 测试电力（单个） ===')
selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    for stock in group['stocks'][:5]:
        print(f"    {stock['stock_code']} {stock['stock_name']}")
