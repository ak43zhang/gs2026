#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从MySQL获取指定时间点的股票数据
"""
import pandas as pd
from sqlalchemy import create_engine

def get_mysql_data():
    # 创建数据库连接
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    # 先列出所有表
    try:
        tables = pd.read_sql("SHOW TABLES", con=engine)
        print(f'找到的表: {list(tables.values.flatten())}')
    except Exception as e:
        print(f'列出表失败: {e}')
        return
    
    # 使用正确的表名
    table_name = 'monitor_gp_sssj_20260626'
    codes = ['688596', '688300', '600481']
    
    for time_str in ['10:00:15', '10:00:18']:
        print(f'\n{"="*60}')
        print(f'时间: {time_str}')
        print(f'{"="*60}')
        
        try:
            # 查询指定时间点的数据
            codes_str = ','.join([f"'{c}'" for c in codes])
            query = f"""
                SELECT * FROM {table_name}
                WHERE time = '{time_str}' AND stock_code IN ({codes_str})
            """
            df = pd.read_sql(query, con=engine)
            
            if df.empty:
                print('数据为空')
                continue
            
            # 检查列名
            print(f'\n所有列名: {list(df.columns)}')
            
            # 打印每只股票的数据
            print(f'\n{"-"*60}')
            print(f'股票详情:')
            print(f'{"-"*60}')
            
            for _, row in df.iterrows():
                code = str(row['stock_code']).zfill(6)
                print(f'\n{code}:')
                
                # 打印关键字段
                key_fields = ['stock_code', 'short_name', 'price', 'change_pct', 'change',
                             'volume', 'amount', 'main_net_count', 'cumulative_main_net',
                             'main_net_amount', 'main_behavior', 'is_zt', 'ever_zt', 'time']
                
                for field in key_fields:
                    if field in row:
                        val = row[field]
                        print(f'  {field}: {val} (type: {type(val).__name__})')
                
                # 检查change_pct是否为0
                change_pct = row.get('change_pct')
                if pd.isna(change_pct) or change_pct == 0:
                    print(f'  ⚠️ change_pct 为0或NaN!')
                
                # 显示完整数据
                print(f'  完整数据: {row.to_dict()}')
                    
        except Exception as e:
            print(f'查询失败: {e}')

if __name__ == '__main__':
    get_mysql_data()
