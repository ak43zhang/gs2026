#!/usr/bin/env python3
"""
验证查询逻辑修改
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

print("=" * 80)
print("验证查询逻辑修改")
print("=" * 80)

# 测试2026-04-28的数据（有累计值）
date = '20260428'
time_str = '15:00:00'
test_codes = ['300243', '300540', '000001', '000002', '000063']

print(f"\n测试参数:")
print(f"  日期: {date}")
print(f"  时间: {time_str}")
print(f"  股票: {test_codes}")

print(f"\n查询结果:")
change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, time_str, test_codes)

for code in test_codes:
    change_pct = change_pct_map.get(code, '-')
    main_net = main_net_map.get(code, 'N/A')
    print(f"  {code}: 涨跌幅={change_pct}, 主力净额(累计)={main_net:,.0f}")

print(f"\n{'='*80}")
print("验证完成")
