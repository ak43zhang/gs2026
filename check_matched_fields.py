#!/usr/bin/env python3
"""检查matched_industries和matched_concepts"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 重新加载缓存
stock_picker_service.load_memory_cache()

selected_tags = [
    {'name': '电力', 'code': '881147', 'type': 'industry'},
    {'name': '电子化学品', 'code': '881173', 'type': 'industry'}
]
result = stock_picker_service.query_cross_stocks(selected_tags)

# 检查前5只股票
print('=== 检查前5只股票的matched字段 ===')
for group in result['groups']:
    for stock in group['stocks'][:5]:
        print(f"{stock['stock_code']}:")
        print(f"  matched_industries: {stock['matched_industries']} (type: {type(stock['matched_industries'])})")
        print(f"  matched_concepts: {stock['matched_concepts']} (type: {type(stock['matched_concepts'])})")
