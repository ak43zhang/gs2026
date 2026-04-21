#!/usr/bin/env python3
"""检查行业/概念/股票数据结构 - 第二部分"""
import sys
sys.path.insert(0, 'src')

from gs2026.utils import config_util
import pandas as pd
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 1. 查看行业-股票关系表
    print('=== 查找行业/概念相关表 ===')
    tables = conn.execute(text("SHOW TABLES LIKE '%%hy%%'")).fetchall()
    for t in tables:
        print(f'  {t[0]}')
    
    tables2 = conn.execute(text("SHOW TABLES LIKE '%%concept%%'")).fetchall()
    for t in tables2:
        print(f'  {t[0]}')
    
    tables3 = conn.execute(text("SHOW TABLES LIKE '%%gn%%'")).fetchall()
    for t in tables3:
        print(f'  {t[0]}')
    
    tables4 = conn.execute(text("SHOW TABLES LIKE '%%industry%%'")).fetchall()
    for t in tables4:
        print(f'  {t[0]}')
    
    # 2. 查看行业成分股表
    print('\n=== data_industry_stock_ths (if exists) ===')
    try:
        df = pd.read_sql('SELECT * FROM data_industry_stock_ths LIMIT 5', conn)
        print('columns:', df.columns.tolist())
        print(df.head(5).to_string())
        cnt = pd.read_sql('SELECT COUNT(*) as c FROM data_industry_stock_ths', conn).iloc[0]['c']
        print(f'total: {cnt}')
    except Exception as e:
        print(f'not found: {e}')
    
    # 3. 查看概念成分股表
    print('\n=== data_concept_stock_ths (if exists) ===')
    try:
        df = pd.read_sql('SELECT * FROM data_concept_stock_ths LIMIT 5', conn)
        print('columns:', df.columns.tolist())
        print(df.head(5).to_string())
        cnt = pd.read_sql('SELECT COUNT(*) as c FROM data_concept_stock_ths', conn).iloc[0]['c']
        print(f'total: {cnt}')
    except Exception as e:
        print(f'not found: {e}')

    # 4. 查看债券表字段名
    print('\n=== data_bond_ths 字段名 ===')
    cols = conn.execute(text("SHOW COLUMNS FROM data_bond_ths")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
    
    # 5. 查看行业表样本（确认字段名）
    print('\n=== data_industry_code_ths 样本 ===')
    cols = conn.execute(text("SHOW COLUMNS FROM data_industry_code_ths")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
