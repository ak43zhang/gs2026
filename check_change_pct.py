#!/usr/bin/env python3
"""检查查询结果中的change_pct"""
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

# 检查前10只股票的change_pct
print('=== 检查前10只股票的change_pct ===')
for group in result['groups']:
    for stock in group['stocks'][:10]:
        print(f"{stock['stock_code']} {stock['stock_name']}: change_pct={stock['change_pct']} (type={type(stock['change_pct'])})")
