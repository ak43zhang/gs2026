#!/usr/bin/env python3
"""查找有交集的行业对"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service
from collections import defaultdict

# 确保缓存已加载
if not stock_picker_service._stock_cache:
    stock_picker_service.load_memory_cache()

# 统计每个行业的股票
industry_stocks = defaultdict(list)
for code, data in stock_picker_service._stock_cache.items():
    for industry in data.get('industries', set()):
        industry_stocks[industry].append(code)

print(f"行业数量: {len(industry_stocks)}")

# 查找有交集的行业对
print("\n=== 有交集的行业对（前10） ===")
cross_pairs = []
industries = list(industry_stocks.keys())
for i, ind1 in enumerate(industries):
    for ind2 in industries[i+1:]:
        cross = set(industry_stocks[ind1]) & set(industry_stocks[ind2])
        if len(cross) > 0:
            cross_pairs.append((ind1, ind2, len(cross)))

cross_pairs.sort(key=lambda x: x[2], reverse=True)
for ind1, ind2, count in cross_pairs[:10]:
    print(f"  {ind1} + {ind2}: {count} 只股票")

# 测试一个有交集的例子
if cross_pairs:
    ind1, ind2, count = cross_pairs[0]
    print(f"\n=== 测试 {ind1} + {ind2} ===")
    selected_tags = [
        {'name': ind1, 'code': 'code1', 'type': 'industry'},
        {'name': ind2, 'code': 'code2', 'type': 'industry'}
    ]
    result = stock_picker_service.query_cross_stocks(selected_tags)
    print(f"查询结果: {result['summary']}")
    for group in result['groups']:
        print(f"  {group['label']}: {len(group['stocks'])} 只股票")
