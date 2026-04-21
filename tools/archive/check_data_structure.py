#!/usr/bin/env python3
"""检查行业/概念/股票数据结构"""
import sys
sys.path.insert(0, 'src')

from gs2026.utils import config_util
import pandas as pd
from sqlalchemy import create_engine

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 1. 行业表
print('=== data_industry_code_ths ===')
df = pd.read_sql('SELECT * FROM data_industry_code_ths LIMIT 3', engine)
print('columns:', df.columns.tolist())
print(df.head(3).to_string())
cnt = pd.read_sql('SELECT COUNT(*) as c FROM data_industry_code_ths', engine).iloc[0]['c']
print(f'total: {cnt}')

# 2. 概念表
print('\n=== data_concept_code_ths (if exists) ===')
try:
    df2 = pd.read_sql('SELECT * FROM data_concept_code_ths LIMIT 3', engine)
    print('columns:', df2.columns.tolist())
    print(df2.head(3).to_string())
    cnt2 = pd.read_sql('SELECT COUNT(*) as c FROM data_concept_code_ths', engine).iloc[0]['c']
    print(f'total: {cnt2}')
except Exception as e:
    print(f'not found: {e}')

# 3. 债券映射表
print('\n=== data_bond_ths ===')
df3 = pd.read_sql('SELECT * FROM data_bond_ths LIMIT 3', engine)
print('columns:', df3.columns.tolist())
print(df3.head(3).to_string())
cnt3 = pd.read_sql('SELECT COUNT(*) as c FROM data_bond_ths', engine).iloc[0]['c']
print(f'total: {cnt3}')

# 4. 股票实时数据表（今天）
print('\n=== 实时股票数据 ===')
try:
    df4 = pd.read_sql('SELECT * FROM monitor_gp_apqd_20260421 LIMIT 3', engine)
    print('columns:', df4.columns.tolist())
    print(df4.head(3).to_string())
except Exception as e:
    print(f'error: {e}')

# 5. 查看行业-股票关系
print('\n=== 行业-股票关系表 ===')
tables = pd.read_sql("SHOW TABLES LIKE '%stock_industry%'", engine)
print(tables.to_string())
tables2 = pd.read_sql("SHOW TABLES LIKE '%hy_gn%'", engine)
print(tables2.to_string())
tables3 = pd.read_sql("SHOW TABLES LIKE '%industry_stock%'", engine)
print(tables3.to_string())
tables4 = pd.read_sql("SHOW TABLES LIKE '%concept%'", engine)
print(tables4.to_string())
