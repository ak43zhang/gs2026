#!/usr/bin/env python3
"""
查找函数调用位置
"""
import re

with open('F:\\pyworkspace2026\\gs2026\\src\\gs2026\\monitor\\monitor_stock.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# 查找函数定义
print("=" * 80)
print("查找 calculate_cumulative_main_net 函数")
print("=" * 80)

for i, line in enumerate(lines, 1):
    if 'calculate_cumulative_main_net' in line:
        print(f"  第{i}行: {line.strip()}")

print("\n" + "=" * 80)
