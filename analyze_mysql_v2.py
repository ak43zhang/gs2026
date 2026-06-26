#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接从MySQL查询指定时间点的股票数据
"""
import pandas as pd
from sqlalchemy import create_engine

def get_mysql_data():
    # 创建数据库连接
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    table_name = 'monitor_gp_sssj_20260626'
    codes = ['688596', '688300', '600481']
    
    for time_str in ['10:00:15', '10:00:18']:
        print(f'\n{"="*80}')
        print(f'时间: {time_str}')
        print(f'{"="*80}')
        
        try:
            # 查询所有股票
            query = f"""
                SELECT stock_code, short_name, price, change_pct, `change`,
                       volume, amount, main_net_count, cumulative_main_net,
                       main_net_amount, main_behavior, is_zt, ever_zt, time
                FROM {table_name}
                WHERE time = '{time_str}'
                ORDER BY stock_code
            """
            df = pd.read_sql(query, con=engine)
            
            print(f'总股票数: {len(df)}')
            
            # 检查缺失的股票
            print(f'\n缺失的股票代码:')
            for code in codes:
                mask = df['stock_code'].astype(str).str.zfill(6) == code
                if not mask.any():
                    print(f'  {code}: 未找到')
            for code in codes:
                mask = df['stock_code'].astype(str).str.zfill(6) == code
                row = df[mask]
                
                if row.empty:
                    print(f'\n{code}: 未找到')
                    continue
                
                print(f'\n{code}:')
                for col in ['stock_code', 'short_name', 'price', 'change_pct', 'change',
                           'volume', 'amount', 'main_net_count', 'cumulative_main_net',
                           'main_net_amount', 'main_behavior', 'is_zt', 'ever_zt', 'time']:
                    if col in row:
                        val = row[col].values[0]
                        print(f'  {col}: {val}')
                
                # 检查change_pct是否为0
                change_pct = row['change_pct'].values[0]
                if change_pct == 0 or pd.isna(change_pct):
                    print(f'  ⚠️ change_pct 异常!')
                    
        except Exception as e:
            print(f'查询失败: {e}')

if __name__ == '__main__':
    get_mysql_data()
