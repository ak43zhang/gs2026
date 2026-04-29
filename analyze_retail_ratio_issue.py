#!/usr/bin/env python3
"""
分析散户占比过低问题，找出根本原因并给出修复方案
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("散户占比过低问题分析")
print("=" * 80)

stocks = ['000925', '000967', '301396']

for stock_code in stocks:
    print(f"\n\n{'='*80}")
    print(f"股票: {stock_code}")
    print(f"{'='*80}")
    
    with engine.connect() as conn:
        df = pd.read_sql(f"""
            SELECT 
                time, 
                price, 
                change_pct,
                volume,
                amount,
                main_net_amount
            FROM monitor_gp_sssj_20260428
            WHERE stock_code = '{stock_code}'
            ORDER BY time
        """, conn)
        
        if len(df) == 0:
            print(f"无数据")
            continue
        
        df['price'] = df['price'].astype(float)
        df['change_pct'] = df['change_pct'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['amount'] = df['amount'].astype(float)
        df['main_net_amount'] = df['main_net_amount'].astype(float)
        
        df['price_diff'] = df['price'].diff()
        df['amount_diff'] = df['amount'].diff()
        df['volume_diff'] = df['volume'].diff()
        
        # 1. 当前散户/主力划分分析
        print(f"\n【1. 当前散户/主力划分（30万门槛）】")
        print(f"{'类型':<15} {'记录数':<10} {'占比':<10} {'成交额':<15} {'成交占比':<10}")
        print("-" * 65)
        
        retail_df = df[df['amount_diff'] < 300000]
        main_df = df[df['amount_diff'] >= 300000]
        
        retail_count = len(retail_df)
        main_count = len(main_df)
        total_count = len(df)
        
        retail_amount = retail_df['amount_diff'].sum()
        main_amount = main_df['amount_diff'].sum()
        total_amount = df['amount_diff'].sum()
        
        print(f"{'散户(<30万)':<15} {retail_count:<10} {retail_count/total_count*100:>8.1f}% {retail_amount:>14,.0f} {retail_amount/total_amount*100:>8.1f}%")
        print(f"{'主力(>=30万)':<15} {main_count:<10} {main_count/total_count*100:>8.1f}% {main_amount:>14,.0f} {main_amount/total_amount*100:>8.1f}%")
        
        # 2. 不同门槛下的分布
        print(f"\n【2. 不同门槛下的分布】")
        print(f"{'门槛':<15} {'散户记录':<12} {'散户占比':<12} {'主力记录':<12} {'主力占比':<12}")
        print("-" * 70)
        
        thresholds = [50000, 100000, 200000, 300000, 500000, 1000000]
        
        for threshold in thresholds:
            retail = df[df['amount_diff'] < threshold]
            main = df[df['amount_diff'] >= threshold]
            
            retail_pct = len(retail) / len(df) * 100
            main_pct = len(main) / len(df) * 100
            
            print(f"{'<'+str(threshold):<15} {len(retail):<12} {retail_pct:>10.1f}% {len(main):<12} {main_pct:>10.1f}%")
        
        # 3. 成交额分布直方图
        print(f"\n【3. 成交额分布】")
        print(f"{'区间':<20} {'记录数':<10} {'占比':<10} {'累计占比':<10}")
        print("-" * 55)
        
        bins = [
            (0, 50000, '<5万'),
            (50000, 100000, '5-10万'),
            (100000, 200000, '10-20万'),
            (200000, 300000, '20-30万'),
            (300000, 500000, '30-50万'),
            (500000, 1000000, '50-100万'),
            (1000000, 2000000, '100-200万'),
            (2000000, 5000000, '200-500万'),
            (5000000, float('inf'), '>500万'),
        ]
        
        cumulative = 0
        for low, high, label in bins:
            if high == float('inf'):
                count = len(df[df['amount_diff'] >= low])
            else:
                count = len(df[(df['amount_diff'] >= low) & (df['amount_diff'] < high)])
            
            pct = count / len(df) * 100
            cumulative += pct
            
            print(f"{label:<20} {count:<10} {pct:>8.1f}% {cumulative:>8.1f}%")
        
        # 4. 问题诊断
        print(f"\n【4. 问题诊断】")
        
        # 计算平均成交额
        avg_amount = df['amount_diff'].mean()
        median_amount = df['amount_diff'].median()
        
        print(f"平均成交额: {avg_amount:,.0f} 元")
        print(f"中位数成交额: {median_amount:,.0f} 元")
        
        # 找出问题
        if median_amount > 100000:
            print(f"\n【问题】中位数成交额过高！")
            print(f"  中位数: {median_amount:,.0f} 元")
            print(f"  说明大部分交易都是大单")
            print(f"  可能原因：")
            print(f"    1. 数据源只包含大单")
            print(f"    2. 小单被过滤掉了")
            print(f"    3. 股票本身流动性差，只有大单")
        
        # 5. 合理门槛计算
        print(f"\n【5. 合理门槛计算】")
        
        # 目标是散户占比60-70%
        target_retail_ratio = 0.65
        
        # 找到使散户占比接近65%的门槛
        amounts = sorted(df['amount_diff'].dropna())
        target_idx = int(len(amounts) * target_retail_ratio)
        optimal_threshold = amounts[target_idx] if target_idx < len(amounts) else amounts[-1]
        
        print(f"目标散户占比: {target_retail_ratio*100:.0f}%")
        print(f"建议门槛: {optimal_threshold:,.0f} 元")
        
        # 验证
        retail_optimal = df[df['amount_diff'] < optimal_threshold]
        main_optimal = df[df['amount_diff'] >= optimal_threshold]
        
        print(f"\n验证:")
        print(f"  散户(<{optimal_threshold:,.0f}): {len(retail_optimal)} 条 ({len(retail_optimal)/len(df)*100:.1f}%)")
        print(f"  主力(>={optimal_threshold:,.0f}): {len(main_optimal)} 条 ({len(main_optimal)/len(df)*100:.1f}%)")
        
        # 6. 修复方案
        print(f"\n【6. 修复方案】")
        
        print(f"\n方案A: 动态门槛（推荐）")
        print(f"  - 根据数据分布动态计算门槛")
        print(f"  - 门槛 = 第65百分位数")
        print(f"  - 本股票建议门槛: {optimal_threshold:,.0f} 元")
        
        print(f"\n方案B: 固定低门槛")
        print(f"  - 门槛降至5万或10万")
        print(f"  - 散户占比可提升至50-60%")
        
        # 计算方案B效果
        for new_threshold in [50000, 100000]:
            retail_new = df[df['amount_diff'] < new_threshold]
            main_new = df[df['amount_diff'] >= new_threshold]
            
            print(f"\n  门槛={new_threshold}:")
            print(f"    散户: {len(retail_new)} 条 ({len(retail_new)/len(df)*100:.1f}%)")
            print(f"    主力: {len(main_new)} 条 ({len(main_new)/len(df)*100:.1f}%)")
        
        print(f"\n方案C: 多档划分")
        print(f"  - 散户: <10万")
        print(f"  - 中户: 10-50万")
        print(f"  - 大户: 50-200万")
        print(f"  - 机构: >=200万")
        
        # 计算方案C
        retail_c = df[df['amount_diff'] < 100000]
        medium_c = df[(df['amount_diff'] >= 100000) & (df['amount_diff'] < 500000)]
        large_c = df[(df['amount_diff'] >= 500000) & (df['amount_diff'] < 2000000)]
        inst_c = df[df['amount_diff'] >= 2000000]
        
        print(f"\n  散户(<10万): {len(retail_c)} 条 ({len(retail_c)/len(df)*100:.1f}%)")
        print(f"  中户(10-50万): {len(medium_c)} 条 ({len(medium_c)/len(df)*100:.1f}%)")
        print(f"  大户(50-200万): {len(large_c)} 条 ({len(large_c)/len(df)*100:.1f}%)")
        print(f"  机构(>=200万): {len(inst_c)} 条 ({len(inst_c)/len(df)*100:.1f}%)")

print(f"\n\n{'='*80}")
print("分析完成")
