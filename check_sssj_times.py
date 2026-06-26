#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 monitor_gp_sssj 表中指定股票在多个时间点的数据
"""
import pandas as pd
from sqlalchemy import create_engine

def check_sssj():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    table_name = 'monitor_gp_sssj_20260626'
    codes = ['688596', '688300', '600481']
    
    # 检查多个时间点
    for time_str in ['10:00:15', '10:00:18', '10:01:00', '10:02:00', '10:05:00', '10:10:00']:
        print(f'\n{"="*80}')
        print(f'时间: {time_str}')
        print(f'{"="*80}')
        
        try:
            query = f"""
                SELECT stock_code, short_name, price, change_pct, `change`,
                       volume, amount, main_net_count, cumulative_main_net,
                       main_net_amount, main_behavior, is_zt, ever_zt, time
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
                print(f"  short_name: {row['short_name']}")
                print(f"  price: {row['price']}")
                print(f"  change_pct: {row['change_pct']}")
                print(f"  main_net_count: {row['main_net_count']}")
                print(f"  time: {row['time']}")
                
        except Exception as e:
            print(f'查询失败: {e}')

if __name__ == '__main__':
    check_sssj()
