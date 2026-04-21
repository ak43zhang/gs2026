#!/usr/bin/env python3
"""验证电力+电子化学品查询结果"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 重新加载缓存
stock_picker_service.load_memory_cache()

print('=== 测试电力 + 电子化学品 ===')
selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'},
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)

print(f"查询标签: {[t['name'] for t in result['tags']]}")
print(f"摘要: {result['summary']}")
print(f"\n分组数量: {len(result['groups'])}")

for group in result['groups']:
    print(f"\n  {group['label']}: {len(group['stocks'])} 只股票")
    # 显示前3只
    for stock in group['stocks'][:3]:
        industries = ','.join(stock['matched_industries'])
        concepts = ','.join(stock['matched_concepts'])
        print(f"    {stock['stock_code']} {stock['stock_name']} | 行业:{industries} | 概念:{concepts}")
