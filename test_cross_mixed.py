#!/usr/bin/env python3
"""测试有交集的行业+概念组合"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 重新加载缓存
stock_picker_service.load_memory_cache()

print('=== 测试半导体行业 + AI应用概念 ===')
selected_tags = [
    {'name': '半导体', 'code': '881121', 'type': 'industry'},
    {'name': 'AI应用', 'code': '886108', 'type': 'concept'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)
print(f"查询结果: {result['summary']}")
for group in result['groups']:
    print(f"  {group['label']}: {len(group['stocks'])} 只股票")
    if len(group['stocks']) > 0:
        print("    示例:")
        for stock in group['stocks'][:3]:
            print(f"      {stock['stock_code']} {stock['stock_name']}")
            print(f"        行业: {stock['matched_industries']}")
            print(f"        概念: {stock['matched_concepts']}")

print()
print('=== 测试电力行业 + 新能源概念 ===')
# 先搜索新能源概念
results = stock_picker_service.search_tags('新能源')
print(f"搜索 新能源: {len(results)} 条结果")
for r in results[:3]:
    print(f"  {r['name']} ({r['type']}) - {r['code']}")

if results:
    selected_tags = [
        {'name': '电力', 'code': '881147', 'type': 'industry'},
        {'name': results[0]['name'], 'code': results[0]['code'], 'type': results[0]['type']}
    ]
    result = stock_picker_service.query_cross_stocks(selected_tags)
    print(f"\n查询结果: {result['summary']}")
    for group in result['groups']:
        print(f"  {group['label']}: {len(group['stocks'])} 只股票")
