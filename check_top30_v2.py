#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 monitor_gp_top30 表的列名
"""
import pandas as pd
from sqlalchemy import create_engine

def check_top30():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    table_name = 'monitor_gp_top30_20260626'
    
    try:
        # 查看列名
        df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 1", con=engine)
        print(f'列名: {list(df.columns)}')
        
        # 查看数据
        df = pd.read_sql(f"SELECT * FROM {table_name} WHERE time = '10:00:15' LIMIT 5", con=engine)
        print(f'\n10:00:15 数据:\n{df}')
        
        df = pd.read_sql(f"SELECT * FROM {table_name} WHERE time = '10:00:18' LIMIT 5", con=engine)
        print(f'\n10:00:18 数据:\n{df}')
        
    except Exception as e:
        print(f'查询失败: {e}')

if __name__ == '__main__':
    check_top30()
