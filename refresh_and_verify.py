#!/usr/bin/env python3
"""重新预热缓存并验证债券数据"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

print("=== 重新预热缓存 ===")
stock_picker_service.warm_up_cache()

print("\n=== 验证债券数据 ===")
stock_picker_service.load_memory_cache()

print(f"内存缓存股票数: {len(stock_picker_service._stock_cache)}")
print(f"债券映射数: {len(stock_picker_service._bond_map)}")

# 显示有债券的股票
if stock_picker_service._bond_map:
    print("\n有债券的股票示例（前5）:")
    for i, (stock_code, bond_info) in enumerate(list(stock_picker_service._bond_map.items())[:5]):
        stock_data = stock_picker_service._stock_cache.get(stock_code, {})
        print(f"  {stock_code} {stock_data.get('stock_name', 'N/A')} -> {bond_info['code']} {bond_info['name']}")
