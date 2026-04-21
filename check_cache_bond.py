#!/usr/bin/env python3
"""检查宽表中的债券数据"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

print("=== 检查宽表中的债券数据 ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("""
        SELECT stock_code, stock_name, bond_code, bond_name 
        FROM cache_stock_industry_concept_bond 
        WHERE bond_code IS NOT NULL AND bond_code != ''
        LIMIT 10
    """, conn)
    print(f"有债券的记录数: {len(df)}")
    print("\n样本数据:")
    for _, row in df.iterrows():
        print(f"  {row['stock_code']} {row['stock_name']} -> {row['bond_code']} {row['bond_name']}")
