#!/usr/bin/env python3
"""检查概念成分股和实时涨跌幅数据"""
import sys
sys.path.insert(0, 'src')

from gs2026.utils import config_util
import pandas as pd
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 1. 概念成分股表 data_gnzscfxx_ths
    print('=== data_gnzscfxx_ths ===')
    cols = conn.execute(text("SHOW COLUMNS FROM data_gnzscfxx_ths")).fetchall()
    for c in cols:
        print(f'  {c[0]} ({c[1]})')
    df = pd.read_sql('SELECT * FROM data_gnzscfxx_ths LIMIT 5', conn)
    print(df.to_string())
    cnt = pd.read_sql('SELECT COUNT(*) as c FROM data_gnzscfxx_ths', conn).iloc[0]['c']
    print(f'total: {cnt}')
    
    # 2. 概念名称列表（去重）
    print('\n=== ths_gn_names 概念名称样本 ===')
    df2 = pd.read_sql('SELECT name, code FROM ths_gn_names ORDER BY name LIMIT 20', conn)
    print(df2.to_string())
    
    # 3. 实时股票涨跌幅数据
    print('\n=== monitor_gp_sssj_20260421 ===')
    try:
        cols = conn.execute(text("SHOW COLUMNS FROM monitor_gp_sssj_20260421")).fetchall()
        for c in cols[:15]:
            print(f'  {c[0]} ({c[1]})')
        df3 = pd.read_sql('SELECT * FROM monitor_gp_sssj_20260421 LIMIT 3', conn)
        print(df3.columns.tolist())
    except Exception as e:
        print(f'not found: {e}')
    
    # 4. 股票top30表（含涨跌幅）
    print('\n=== monitor_gp_top30_20260421 ===')
    try:
        cols = conn.execute(text("SHOW COLUMNS FROM monitor_gp_top30_20260421")).fetchall()
        for c in cols:
            print(f'  {c[0]} ({c[1]})')
        df4 = pd.read_sql('SELECT * FROM monitor_gp_top30_20260421 LIMIT 3', conn)
        print(df4.to_string())
    except Exception as e:
        print(f'not found: {e}')

    # 5. 债券表字段名（中文字段名确认）
    print('\n=== data_bond_ths 列名 ===')
    cols = conn.execute(text("SHOW COLUMNS FROM data_bond_ths")).fetchall()
    for c in cols:
        print(f'  {c[0]}')
