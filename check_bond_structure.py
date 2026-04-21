#!/usr/bin/env python3
"""检查 data_bond_ths 表结构"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("SHOW COLUMNS FROM data_bond_ths", conn)
    print("表结构:")
    for i, row in df.iterrows():
        print(f"  {i}: {row['Field']} ({row['Type']})")

with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("SELECT * FROM data_bond_ths LIMIT 1", conn)
    print("\n样本数据（按列索引）:")
    for i, (col, val) in enumerate(zip(df.columns, df.iloc[0].values)):
        print(f"  [{i}] {col}: {val}")
