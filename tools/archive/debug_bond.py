#!/usr/bin/env python3
"""调试债券映射"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

print("=== 检查 data_bond_ths 表 ===")
with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT * FROM data_bond_ths", conn).to_dict('records')

print(f"总行数: {len(rows)}")

if rows:
    print("\n第一行数据:")
    row = rows[0]
    values = list(row.values())
    for i, (k, v) in enumerate(zip(row.keys(), values)):
        print(f"  [{i}] {k}: {v}")
    
    print(f"\n尝试获取:")
    print(f"  values[4] (正股代码): {values[4]}")
    print(f"  values[1] (债券代码): {values[1]}")
    print(f"  values[2] (债券名称): {values[2]}")
    
    # 构建bond_map
    bond_map = {}
    for row in rows:
        values = list(row.values())
        stock_code = values[4]
        bond_code = values[1]
        bond_name = values[2]
        if stock_code:
            bond_map[stock_code] = {'code': bond_code, 'name': bond_name}
    
    print(f"\nbond_map 数量: {len(bond_map)}")
    print("示例（前5）:")
    for i, (k, v) in enumerate(list(bond_map.items())[:5]):
        print(f"  {k} -> {v}")
