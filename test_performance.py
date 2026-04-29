#!/usr/bin/env python3
"""
测试优化后的查询性能
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import time
from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

print("=" * 80)
print("查询性能测试")
print("=" * 80)

# 测试参数
date = '20260428'
time_str = '15:00:00'
stock_codes = ['000001', '000002', '000063', '000333', '000538', '000568', 
               '000625', '000651', '000725', '000768', '000858', '000895',
               '002001', '002007', '002024', '002027', '002142', '002230',
               '002236', '002271', '002304', '002352', '002415', '002460',
               '002475', '002594', '002714', '002812', '003816', '300003',
               '300014', '300015', '300033', '300059', '300122', '300124',
               '300274', '300408', '300413', '300433', '300498', '300750',
               '600000', '600009', '600016', '600028', '600030', '600031',
               '600036', '600048', '600050', '600104', '600276', '600309',
               '600406', '600436', '600438', '600519', '600585', '600588']

print(f"\n测试参数:")
print(f"  日期: {date}")
print(f"  时间: {time_str}")
print(f"  股票数: {len(stock_codes)}")

# 测试优化后的查询
print(f"\n【优化后】批量查询涨跌幅和主力净额...")
start_time = time.time()
change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, time_str, stock_codes)
elapsed = time.time() - start_time

print(f"  耗时: {elapsed:.3f}秒")
print(f"  涨跌幅: {len(change_pct_map)}条")
print(f"  主力净额: {len(main_net_map)}条")

# 显示部分结果
print(f"\n样例结果:")
for code in stock_codes[:5]:
    change_pct = change_pct_map.get(code, '-')
    main_net = main_net_map.get(code, 0)
    print(f"  {code}: 涨跌幅={change_pct}, 主力净额={main_net:,.0f}")

print(f"\n{'='*80}")
print("测试完成")
