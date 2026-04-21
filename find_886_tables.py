#!/usr/bin/env python3
"""查找886开头的概念代码"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 检查所有表
with mysql_tool.engine.connect() as conn:
    tables = pd.read_sql("SHOW TABLES", conn)
    all_tables = tables.iloc[:, 0].tolist()

# 查找可能包含概念名称的表
for table in all_tables:
    if 'gn' in table.lower() or 'concept' in table.lower():
        try:
            with mysql_tool.engine.connect() as conn:
                df = pd.read_sql(f'SELECT * FROM {table} LIMIT 1', conn)
                cols = df.columns.tolist()
                if 'code' in cols or '886' in str(df.iloc[0].tolist()):
                    print(f'\n=== {table} ===')
                    print(f'列: {cols}')
                    print(f'样本: {df.iloc[0].to_dict()}')
        except:
            pass
