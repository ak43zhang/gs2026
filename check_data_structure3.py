#!/usr/bin/env python3
"""检查行业成分股和概念成分股"""
import sys
sys.path.insert(0, 'src')

from gs2026.utils import config_util
import pandas as pd
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 1. 行业成分股表
    print('=== data_industry_code_component_ths ===')
    cols = conn.execute(text("SHOW COLUMNS FROM data_industry_code_component_ths")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
    df = pd.read_sql('SELECT * FROM data_industry_code_component_ths LIMIT 5', conn)
    print(df.to_string())
    cnt = pd.read_sql('SELECT COUNT(*) as c FROM data_industry_code_component_ths', conn).iloc[0]['c']
    print(f'total: {cnt}')
    
    # 2. 概念成分股表 ths_gn_bk
    print('\n=== ths_gn_bk ===')
    cols = conn.execute(text("SHOW COLUMNS FROM ths_gn_bk")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
    df2 = pd.read_sql('SELECT * FROM ths_gn_bk LIMIT 5', conn)
    print(df2.to_string())
    cnt2 = pd.read_sql('SELECT COUNT(*) as c FROM ths_gn_bk', conn).iloc[0]['c']
    print(f'total: {cnt2}')
    
    # 3. 概念名称表
    print('\n=== ths_gn_names ===')
    cols = conn.execute(text("SHOW COLUMNS FROM ths_gn_names")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
    df3 = pd.read_sql('SELECT * FROM ths_gn_names LIMIT 5', conn)
    print(df3.to_string())
    cnt3 = pd.read_sql('SELECT COUNT(*) as c FROM ths_gn_names', conn).iloc[0]['c']
    print(f'total: {cnt3}')

    # 4. 债券表（查看正股代码和债券代码字段）
    print('\n=== data_bond_ths 样本 ===')
    df4 = pd.read_sql('SELECT * FROM data_bond_ths LIMIT 3', conn)
    for col in df4.columns:
        print(f'  {col}: {df4[col].iloc[0]}')
