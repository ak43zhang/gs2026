# -*- coding: utf-8 -*-
"""
模拟API调用，检查实际返回的JSON数据
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config
from collections import defaultdict

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

with engine.connect() as conn:
    # 模拟API查询
    sql = text("""
        SELECT * FROM quant_screen_hits 
        WHERE trade_date = :date
        ORDER BY id DESC
        LIMIT 3
    """)
    
    df = pd.read_sql(sql, conn, params={'date': today})
    
    # 替换NaN为None
    df = df.replace({float('nan'): None, float('inf'): None, float('-inf'): None})
    
    # 转换数据
    hits = df.to_dict('records')
    
    # 格式化时间
    for hit in hits:
        if 'tick_time' in hit:
            hit['tick_time'] = str(hit['tick_time'])
        if 'created_at' in hit:
            hit['created_at'] = str(hit['created_at'])
        if 'locked_at' in hit and hit['locked_at']:
            hit['locked_at'] = str(hit['locked_at'])
    
    # 检查数据类型
    print('API返回数据类型检查:')
    print('='*80)
    
    for hit in hits:
        print(f'\nID:{hit["id"]} {hit["bond_code"]}')
        print(f'  is_locked: {hit["is_locked"]} (type: {type(hit["is_locked"]).__name__})')
        print(f'  final_return_pct: {hit["final_return_pct"]} (type: {type(hit["final_return_pct"]).__name__ if hit["final_return_pct"] is not None else "None"})')
        print(f'  signal_status: {hit["signal_status"]}')
        
        # 检查is_locked的值
        if isinstance(hit['is_locked'], (int, float)):
            print(f'  ⚠️ is_locked是数字类型，需要转换为bool')
            is_locked_bool = bool(hit['is_locked'])
            print(f'  转换后: {is_locked_bool}')
        
        # 检查final_return_pct是否为Decimal类型
        from decimal import Decimal
        if isinstance(hit['final_return_pct'], Decimal):
            print(f'  ⚠️ final_return_pct是Decimal类型，需要转换为float')
            f_rp = float(hit['final_return_pct'])
            print(f'  转换后: {f_rp} (type: {type(f_rp).__name__})')

print('\n' + '='*80)
print('检查完成')
