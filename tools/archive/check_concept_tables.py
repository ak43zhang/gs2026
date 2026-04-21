#!/usr/bin/env python3
"""检查概念相关表结构"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 检查三个表的结构
tables = ['data_gnzscfxx_ths', 'data_gnzsxx_ths', 'data_dzgpssgn_ths']

for table in tables:
    print(f"\n=== {table} ===")
    try:
        with mysql_tool.engine.connect() as conn:
            df = pd.read_sql(f'SHOW COLUMNS FROM {table}', conn)
            print(f"列数: {len(df)}")
            for _, row in df.iterrows():
                print(f"  {row['Field']}: {row['Type']}")
        
        with mysql_tool.engine.connect() as conn:
            df = pd.read_sql(f'SELECT * FROM {table} LIMIT 2', conn)
            print("样本数据:")
            for col in df.columns[:5]:  # 只显示前5列
                print(f"  {col}: {df[col].iloc[0]}")
    except Exception as e:
        print(f"错误: {e}")
