#!/usr/bin/env python3
"""
填充历史数据的主力净额字段
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--date', required=True, help='日期格式: 2026-04-24')
args = parser.parse_args()

date_str = args.date.replace('-', '')
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print(f"=" * 80)
print(f"填充 {args.date} 的主力净额数据")
print(f"=" * 80)

with engine.connect() as conn:
    # 1. 读取数据
    print(f"\n【1】读取数据...")
    df = pd.read_sql(f"""
        SELECT 
            stock_code,
            time,
            price,
            change_pct,
            amount,
            volume
        FROM monitor_gp_sssj_{date_str}
        ORDER BY stock_code, time
    """, conn)
    
    print(f"  总记录数: {len(df)}")
    print(f"  股票数: {df['stock_code'].nunique()}")
    
    # 2. 计算主力净额
    print(f"\n【2】计算主力净额...")
    
    # 按股票分组计算
    all_results = []
    stock_codes = df['stock_code'].unique()
    
    for i, code in enumerate(stock_codes):
        if i % 100 == 0:
            print(f"  处理: {i}/{len(stock_codes)} {code}")
        
        stock_df = df[df['stock_code'] == code].copy()
        stock_df = stock_df.sort_values('time')
        
        # 计算变化量
        stock_df['price_diff'] = stock_df['price'].astype(float).diff()
        stock_df['amount_diff'] = stock_df['amount'].astype(float).diff()
        
        # 计算主力净额
        stock_df['main_net_amount'] = 0.0
        stock_df['cumulative_main_net'] = 0.0
        stock_df['main_behavior'] = None
        stock_df['main_confidence'] = 0.0
        
        cumulative = 0.0
        for idx, row in stock_df.iterrows():
            price_diff = row['price_diff']
            amount_diff = row['amount_diff']
            
            if pd.isna(price_diff) or amount_diff <= 0:
                continue
            
            # 方向判断
            if price_diff > 0:
                direction = 1
                behavior = '买入'
            elif price_diff < 0:
                direction = -1
                behavior = '卖出'
            else:
                direction = 0
                behavior = None
            
            # 参与系数
            if amount_diff >= 2000000:
                confidence = 1.0
            elif amount_diff >= 1000000:
                confidence = 0.8
            elif amount_diff >= 500000:
                confidence = 0.6
            elif amount_diff >= 300000:
                confidence = 0.4
            else:
                confidence = 0.0
            
            main_net = amount_diff * confidence * direction
            cumulative += main_net
            
            stock_df.at[idx, 'main_net_amount'] = main_net
            stock_df.at[idx, 'cumulative_main_net'] = cumulative
            stock_df.at[idx, 'main_behavior'] = behavior
            stock_df.at[idx, 'main_confidence'] = confidence
        
        all_results.append(stock_df[['stock_code', 'time', 'main_net_amount', 'cumulative_main_net', 'main_behavior', 'main_confidence']])
    
    # 3. 更新数据库
    print(f"\n【3】更新数据库...")
    result_df = pd.concat(all_results, ignore_index=True)
    
    # 分批更新
    batch_size = 10000
    total = len(result_df)
    
    for i in range(0, total, batch_size):
        batch = result_df.iloc[i:i+batch_size]
        
        for _, row in batch.iterrows():
            conn.execute(text(f"""
                UPDATE monitor_gp_sssj_{date_str}
                SET main_net_amount = {row['main_net_amount']},
                    cumulative_main_net = {row['cumulative_main_net']},
                    main_behavior = {'\"' + row['main_behavior'] + '\"' if row['main_behavior'] else 'NULL'},
                    main_confidence = {row['main_confidence']}
                WHERE stock_code = '{row['stock_code']}' AND time = '{row['time']}'
            """))
        
        conn.commit()
        print(f"  更新: {min(i+batch_size, total)}/{total}")
    
    print(f"\n【4】验证结果...")
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as non_zero
        FROM monitor_gp_sssj_{date_str}
    """))
    row = result.fetchone()
    print(f"  总记录: {row[0]}")
    print(f"  非零主力净额: {row[1]}")

print(f"\n{'='*80}")
print("填充完成")
