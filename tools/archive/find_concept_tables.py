#!/usr/bin/env python3
"""查找概念相关表"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

with mysql_tool.engine.connect() as conn:
    tables = pd.read_sql("SHOW TABLES LIKE '%gn%'", conn)
    print('包含gn的表:')
    for t in tables.iloc[:, 0]:
        print(f'  {t}')

print()
with mysql_tool.engine.connect() as conn:
    tables = pd.read_sql("SHOW TABLES LIKE '%concept%'", conn)
    print('包含concept的表:')
    for t in tables.iloc[:, 0]:
        print(f'  {t}')

# 检查data_gnzscfxx_ths的样本
print()
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT * FROM data_gnzscfxx_ths LIMIT 3', conn)
    print('data_gnzscfxx_ths 样本:')
    for col in df.columns:
        print(f'  {col}: {df[col].iloc[0]}')
