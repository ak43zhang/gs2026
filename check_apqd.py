#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 monitor_gp_apqd 表中指定股票的数据
"""
import pandas as pd
from sqlalchemy import create_engine

def check_apqd():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    table_name = 'monitor_gp_apqd_20260626'
    
    # 先查看列名
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 1", con=engine)
        print(f'列名: {list(df.columns)}')
    except Exception as e:
        print(f'查看列名失败: {e}')
        return
    
    codes = ['688596', '688300', '600481']
    
    for time_str in ['10:00:15', '10:00:18']:
        print(f'\n{"="*80}')
        print(f'时间: {time_str}')
        print(f'{"="*80}')
        
        try:
            query = f"""
                SELECT *
                FROM {table_name}
                WHERE time = '{time_str}'
                  AND stock_code IN ('688596', '688300', '600481')
            """
            df = pd.read_sql(query, con=engine)
            
            if df.empty:
                print('数据为空')
                continue
            
            for _, row in df.iterrows():
                print(f"\n{row['stock_code']}:")
                for col in df.columns:
                    print(f"  {col}: {row[col]}")
                
        except Exception as e:
            print(f'查询失败: {e}')

if __name__ == '__main__':
    check_apqd()
