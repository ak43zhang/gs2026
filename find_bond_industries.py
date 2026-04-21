#!/usr/bin/env python3
"""查找有转债数据的行业"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 加载缓存
stock_picker_service.load_memory_cache()

cache = stock_picker_service._stock_cache
bond_map = stock_picker_service._bond_map

print(f"总股票数: {len(cache)}")
print(f"有债券的股票数: {len(bond_map)}")

# 统计每个行业的有债券股票数
from collections import defaultdict
industry_bond_count = defaultdict(int)
industry_total_count = defaultdict(int)

for code, data in cache.items():
    for industry in data.get('industries', set()):
        industry_total_count[industry] += 1
        if code in bond_map:
            industry_bond_count[industry] += 1

print("\n=== 有债券的行业（前10） ===")
sorted_industries = sorted(industry_bond_count.items(), key=lambda x: x[1], reverse=True)
for industry, count in sorted_industries[:10]:
    total = industry_total_count[industry]
    print(f"  {industry}: {count}/{total} 只股票有债券")

# 找一个有债券的行业详细查看
if sorted_industries:
    sample_industry = sorted_industries[0][0]
    print(f"\n=== {sample_industry} 行业有债券的股票 ===")
    count = 0
    for code, data in cache.items():
        if sample_industry in data.get('industries', set()) and code in bond_map:
            bond = bond_map[code]
            print(f"  {code} {data['stock_name']} -> 债券: {bond['code']} {bond['name']}")
            count += 1
            if count >= 5:
                break
