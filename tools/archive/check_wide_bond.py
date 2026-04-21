#!/usr/bin/env python3
"""检查宽表中的债券数据"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN bond_code IS NOT NULL AND bond_code != '' THEN 1 ELSE 0 END) as with_bond
        FROM cache_stock_industry_concept_bond
    """, conn)
    print(f"总记录数: {df.iloc[0]['total']}")
    print(f"有债券的记录数: {df.iloc[0]['with_bond']}")

with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("""
        SELECT stock_code, stock_name, bond_code, bond_name
        FROM cache_stock_industry_concept_bond
        WHERE bond_code IS NOT NULL AND bond_code != ''
        LIMIT 10
    """, conn)
    print("\n有债券的股票示例:")
    print(df.to_string())
