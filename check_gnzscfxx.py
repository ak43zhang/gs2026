#!/usr/bin/env python3
"""检查data_gnzscfxx_ths表结构"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 检查表结构
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SHOW COLUMNS FROM data_gnzscfxx_ths', conn)
    print('data_gnzscfxx_ths 表结构:')
    for _, row in df.iterrows():
        print(f"  {row['Field']}: {row['Type']}")

# 获取样本数据
print()
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT * FROM data_gnzscfxx_ths LIMIT 2', conn)
    print('样本数据:')
    print(df.to_string())
