#!/usr/bin/env python3
"""检查缓存数据"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 确保缓存已加载
if not stock_picker_service._stock_cache:
    stock_picker_service.load_memory_cache()

print(f"缓存股票数量: {len(stock_picker_service._stock_cache)}")

# 查找有电力的股票
electric_stocks = []
for code, data in stock_picker_service._stock_cache.items():
    if '电力' in data.get('industries', set()):
        electric_stocks.append(code)

print(f"有电力的股票数量: {len(electric_stocks)}")
if electric_stocks:
    print(f"示例: {electric_stocks[:5]}")
    # 查看第一只股票的详细信息
    sample = stock_picker_service._stock_cache[electric_stocks[0]]
    print(f"  行业: {sample['industries']}")
    print(f"  概念: {sample['concepts']}")

# 查找有电子化学品的股票
chem_stocks = []
for code, data in stock_picker_service._stock_cache.items():
    if '电子化学品' in data.get('industries', set()):
        chem_stocks.append(code)

print(f"有电子化学品的股票数量: {len(chem_stocks)}")
if chem_stocks:
    print(f"示例: {chem_stocks[:5]}")

# 查找同时有的
cross = set(electric_stocks) & set(chem_stocks)
print(f"同时有电力和电子化学品的股票数量: {len(cross)}")
if cross:
    print(f"示例: {list(cross)[:5]}")
