#!/usr/bin/env python
"""测试 monitor_bond.py 的数据库写入"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from datetime import datetime
from gs2026.monitor import monitor_stock as msac

# 创建测试数据
df = pd.DataFrame({
    'bond_code': ['123001', '123002'],
    'bond_name': ['测试债券1', '测试债券2'],
    'price': [100.0, 101.0],
    'change_pct': [1.0, 2.0],
    'time': ['14:30:00', '14:30:00']
})

print("测试数据:")
print(df)
print()

# 测试写入
table_name = "monitor_zq_sssj_20260525"
time_full = "14:30:00"
expire_seconds = 3600

print(f"写入表: {table_name}")
print(f"时间: {time_full}")
print()

try:
    msac.save_dataframe(df, table_name, time_full, expire_seconds)
    print("✓ 写入成功")
except Exception as e:
    print(f"✗ 写入失败: {e}")
    import traceback
    traceback.print_exc()
