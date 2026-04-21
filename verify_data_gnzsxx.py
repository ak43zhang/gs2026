#!/usr/bin/env python3
"""验证 data_gnzsxx_ths 表数据完整性"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

print("=== 验证 data_gnzsxx_ths 表 ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT COUNT(DISTINCT index_code) as concept_count, COUNT(DISTINCT name) as name_count FROM data_gnzsxx_ths', conn)
    print(f"唯一概念代码数(886): {df.iloc[0]['concept_count']}")
    print(f"唯一概念名称数: {df.iloc[0]['name_count']}")

print("\n=== 验证 data_gnzscfxx_ths 表 ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT COUNT(DISTINCT index_code) as concept_count, COUNT(DISTINCT stock_code) as stock_count FROM data_gnzscfxx_ths', conn)
    print(f"唯一概念代码数(886): {df.iloc[0]['concept_count']}")
    print(f"唯一股票数: {df.iloc[0]['stock_count']}")

print("\n=== 检查交集 ===")
with mysql_tool.engine.connect() as conn:
    codes1 = set(pd.read_sql('SELECT DISTINCT index_code FROM data_gnzsxx_ths', conn)['index_code'].tolist())
    codes2 = set(pd.read_sql('SELECT DISTINCT index_code FROM data_gnzscfxx_ths', conn)['index_code'].tolist())
    
print(f"data_gnzsxx_ths 中的概念代码数: {len(codes1)}")
print(f"data_gnzscfxx_ths 中的概念代码数: {len(codes2)}")
print(f"交集数: {len(codes1 & codes2)}")
print(f"只在成分股表中的代码数: {len(codes2 - codes1)}")

if codes2 - codes1:
    print("\n示例（无名称映射的概念代码）:")
    for code in list(codes2 - codes1)[:5]:
        print(f"  {code}")

print("\n=== data_gnzsxx_ths 样本 ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT DISTINCT index_code, name FROM data_gnzsxx_ths LIMIT 10', conn)
    print(df.to_string())
