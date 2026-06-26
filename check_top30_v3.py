#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 monitor_gp_top30 表中指定股票的数据
"""
import pandas as pd
from sqlalchemy import create_engine

def check_top30():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    table_name = 'monitor_gp_top30_20260626'
    codes = ['688596', '688300', '600481']
    
    for time_str in ['10:00:15', '10:00:18']:
        print(f'\n{"="*80}')
        print(f'时间: {time_str}')
        print(f'{"="*80}')
        
        try:
            query = f"""
                SELECT code, name, price_now, change_pct_now, volume_now, amount_now,
                       main_net_amount, window_count, time
                FROM {table_name}
                WHERE time = '{time_str}'
                  AND code IN ('688596', '688300', '600481')
            """
            df = pd.read_sql(query, con=engine)
            
            if df.empty:
                print('数据为空（股票不在top30中）')
                continue
            
            for _, row in df.iterrows():
                print(f"\n{row['code']}:")
                print(f"  name: {row['name']}")
                print(f"  price_now: {row['price_now']}")
                print(f"  change_pct_now: {row['change_pct_now']}")
                print(f"  volume_now: {row['volume_now']}")
                print(f"  amount_now: {row['amount_now']}")
                print(f"  main_net_amount: {row['main_net_amount']}")
                print(f"  window_count: {row['window_count']}")
                print(f"  time: {row['time']}")
                
        except Exception as e:
            print(f'查询失败: {e}')

if __name__ == '__main__':
    check_top30()
