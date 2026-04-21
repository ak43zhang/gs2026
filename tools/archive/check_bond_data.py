#!/usr/bin/env python3
"""检查债券数据"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

print("=== 检查 data_bond_ths 表 ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("SELECT COUNT(*) as c FROM data_bond_ths", conn)
    print(f"总行数: {df.iloc[0]['c']}")

with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("SELECT * FROM data_bond_ths LIMIT 3", conn)
    print("\n样本数据:")
    print(df.to_string())
    print(f"\n列名: {df.columns.tolist()}")
