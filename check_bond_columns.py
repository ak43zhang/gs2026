#!/usr/bin/env python3
"""检查债券表的其他列"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT * FROM data_bond_ths LIMIT 5", conn).to_dict('records')

print("检查各列是否包含标准股票代码（6位数字）:")
for i, row in enumerate(rows):
    print(f"\n第{i+1}行:")
    values = list(row.values())
    for j, (k, v) in enumerate(zip(row.keys(), values)):
        v_str = str(v) if v is not None else ''
        # 检查是否是6位数字
        if len(v_str) == 6 and v_str.isdigit():
            print(f"  [{j}] {k}: {v} <-- 可能是股票代码")
        elif '股票' in k or '正股' in k:
            print(f"  [{j}] {k}: {v}")
