#!/usr/bin/env python3
"""
按照新方案（排除集合竞价 + 早盘被动降权 + 提高门槛）
分析301396数据
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("301396 新方案分析")
print("=" * 80)
print("\n新方案：排除集合竞价 + 早盘被动降权 + 提高门槛")
print()

with engine.connect() as conn:
    # 获取数据
    df = pd.read_sql("""
        SELECT 
            time, 
            price, 
            change_pct,
            volume,
            amount,
            main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '301396'
        ORDER BY time
    """, conn)
    
    if len(df) == 0:
        print("【错误】301396无数据")
        sys.exit(1)
    
    df['price'] = df['price'].astype(float)
    df['change_pct'] = df['change_pct'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['amount'] = df['amount'].astype(float)
    df['main_net_amount'] = df['main_net_amount'].astype(float)
    
    # 计算变化量
    df['price_diff'] = df['price'].diff()
    df['volume_diff'] = df['volume'].diff()
    df['amount_diff'] = df['amount'].diff()
    df['change_diff'] = df['change_pct'].diff()
    
    # 1. 当前数据概览
    print("【1. 当前数据概览】")
    print("=" * 80)
    
    print(f"总记录数: {len(df)}")
    print(f"价格范围: {df['price'].min():.2f} ~ {df['price'].max():.2f}")
    print(f"涨跌幅范围: {df['change_pct'].min():.2f}% ~ {df['change_pct'].max():.2f}%")
    print(f"当前主力净额总和: {df['main_net_amount'].sum():,.0f} 元")
    
    # 全天走势描述
    first_price = df.iloc[0]['price']
    last_price = df.iloc[-1]['price']
    first_change = df.iloc[0]['change_pct']
    last_change = df.iloc[-1]['change_pct']
    
    print(f"\n全天走势:")
    print(f"  开盘: {first_price:.2f} ({first_change:.2f}%)")
    print(f"  收盘: {last_price:.2f} ({last_change:.2f}%)")
    print(f"  涨跌: {last_change - first_change:.2f}%")
    
    if last_change > 9.5:
        trend = "涨停"
    elif last_change > 5:
        trend = "大涨"
    elif last_change > 0:
        trend = "上涨"
    elif last_change > -5:
        trend = "下跌"
    else:
        trend = "大跌"
    
    print(f"  走势类型: {trend}")
    
    # 2. 检查集合竞价数据
    print("\n\n【2. 集合竞价数据检查】")
    print("=" * 80)
    
    auction_data = df[df['time'] < '09:30:00']
    print(f"集合竞价记录数: {len(auction_data)}")
    
    if len(auction_data) > 0:
        print("\n集合竞价数据:")
        print(auction_data[['time', 'price', 'change_pct', 'main_net_amount']].to_string(index=False))
        
        auction_main_net = auction_data['main_net_amount'].sum()
        print(f"\n集合竞价主力净额: {auction_main_net:,.0f} 元")
    else:
        print("无集合竞价数据")
    
    # 3. 早盘数据分析（9:30-9:45）
    print("\n\n【3. 早盘数据分析（9:30-9:45）】")
    print("=" * 80)
    
    morning = df[(df['time'] >= '09:30:00') & (df['time'] < '09:45:00')].copy()
    
    print(f"早盘记录数: {len(morning)}")
    print(f"早盘成交额: {morning['amount_diff'].sum():,.0f} 元")
    print(f"早盘主力净额: {morning['main_net_amount'].sum():,.0f} 元")
    print(f"早盘占全天比例: {morning['main_net_amount'].sum()/df['main_net_amount'].sum()*100:.1f}%")
    
    # 分析早盘的主动/被动交易
    morning['trade_type'] = 'normal'
    
    for idx, row in morning.iterrows():
        change_pct = row['change_pct']
        price_diff = row['price_diff']
        
        if pd.isna(price_diff):
            continue
        
        # 判断交易类型
        if change_pct < -2 and price_diff > 0:
            morning.at[idx, 'trade_type'] = 'passive_buy'
        elif change_pct > 2 and price_diff < 0:
            morning.at[idx, 'trade_type'] = 'passive_sell'
        elif change_pct > 0 and price_diff > 0:
            morning.at[idx, 'trade_type'] = 'active_buy'
        elif change_pct < 0 and price_diff < 0:
            morning.at[idx, 'trade_type'] = 'active_sell'
    
    # 统计早盘交易类型
    print(f"\n早盘交易类型分布:")
    trade_type_stats = morning['trade_type'].value_counts()
    for trade_type, count in trade_type_stats.items():
        type_main_net = morning[morning['trade_type'] == trade_type]['main_net_amount'].sum()
        print(f"  {trade_type}: {count} 条, 主力净额 {type_main_net:,.0f} 元")
    
    # 4. 新方案计算
    print("\n\n【4. 新方案计算】")
    print("=" * 80)
    
    df_new = df.copy()
    
    # 步骤1: 排除集合竞价
    df_new = df_new[df_new['time'] >= '09:30:00']
    print(f"\n步骤1 - 排除集合竞价:")
    print(f"  剩余记录数: {len(df_new)}")
    print(f"  主力净额: {df_new['main_net_amount'].sum():,.0f} 元")
    
    # 步骤2: 早盘被动降权
    morning_mask = (df_new['time'] >= '09:30:00') & (df_new['time'] < '09:45:00')
    
    for idx, row in df_new[morning_mask].iterrows():
        change_pct = row['change_pct']
        price_diff = row['price_diff']
        
        if pd.isna(price_diff):
            continue
        
        # 被动买入降权70%
        if change_pct < -2 and price_diff > 0:
            df_new.at[idx, 'main_net_amount'] *= 0.3
        # 被动卖出降权70%
        elif change_pct > 2 and price_diff < 0:
            df_new.at[idx, 'main_net_amount'] *= 0.3
    
    print(f"\n步骤2 - 早盘被动降权:")
    print(f"  主力净额: {df_new['main_net_amount'].sum():,.0f} 元")
    
    # 步骤3: 提高门槛 + 降低参与系数
    def new_participation(amount):
        if amount < 1000000:
            return 0
        elif amount < 5000000:
            return 0.15
        else:
            return 0.25
    
    # 重新计算主力净额
    df_new['new_main_net'] = 0.0
    
    for idx, row in df_new.iterrows():
        amount_diff = row['amount_diff']
        price_diff = row['price_diff']
        
        if pd.isna(price_diff) or amount_diff <= 0:
            continue
        
        # 方向
        direction = 1 if price_diff > 0 else (-1 if price_diff < 0 else 0)
        
        # 参与系数
        participation = new_participation(amount_diff)
        
        # 早盘被动降权
        time_str = row['time']
        if '09:30:00' <= time_str < '09:45:00':
            change_pct = row['change_pct']
            if change_pct < -2 and price_diff > 0:
                participation *= 0.3  # 被动买入再降权
            elif change_pct > 2 and price_diff < 0:
                participation *= 0.3  # 被动卖出再降权
        
        df_new.at[idx, 'new_main_net'] = amount_diff * participation * direction
    
    new_total = df_new['new_main_net'].sum()
    print(f"\n步骤3 - 提高门槛+降低系数:")
    print(f"  新主力净额: {new_total:,.0f} 元 ({new_total/10000:.0f}万)")
    
    # 5. 对比分析
    print("\n\n【5. 对比分析】")
    print("=" * 80)
    
    old_total = df['main_net_amount'].sum()
    
    print(f"\n方案对比:")
    print(f"{'方案':<20} {'主力净额':<20} {'变化':<15}")
    print("-" * 60)
    print(f"{'当前方案':<20} {old_total:>15,.0f} {'':<15}")
    print(f"{'新方案':<20} {new_total:>15,.0f} {(new_total-old_total)/old_total*100:>+14.1f}%")
    
    # 6. 详细分析早盘关键交易
    print("\n\n【6. 早盘关键交易分析】")
    print("=" * 80)
    
    morning_detailed = df[(df['time'] >= '09:30:00') & (df['time'] < '09:35:00')].head(20)
    
    if len(morning_detailed) > 0:
        print(f"\n早盘前20笔交易:")
        print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'价格变化':<10} {'成交额':<12} {'原净额':<12} {'新净额':<12} {'类型':<15}")
        print("-" * 110)
        
        for idx, row in morning_detailed.iterrows():
            time_str = row['time']
            price = row['price']
            change_pct = row['change_pct']
            price_diff = row['price_diff']
            amount_diff = row['amount_diff']
            old_main_net = row['main_net_amount']
            
            # 计算新净额
            if pd.isna(price_diff) or amount_diff <= 0:
                new_main_net_val = 0
                trade_type = '首笔/无效'
            else:
                direction = 1 if price_diff > 0 else (-1 if price_diff < 0 else 0)
                participation = new_participation(amount_diff)
                
                # 判断类型
                if change_pct < -2 and price_diff > 0:
                    trade_type = 'passive_buy'
                    participation *= 0.3
                elif change_pct > 2 and price_diff < 0:
                    trade_type = 'passive_sell'
                    participation *= 0.3
                elif change_pct > 0 and price_diff > 0:
                    trade_type = 'active_buy'
                elif change_pct < 0 and price_diff < 0:
                    trade_type = 'active_sell'
                else:
                    trade_type = 'normal'
                
                new_main_net_val = amount_diff * participation * direction
            
            print(f"{time_str:<12} {price:<8.2f} {change_pct:<10.2f} {price_diff:<10.2f} {amount_diff:<12.0f} {old_main_net:<12.0f} {new_main_net_val:<12.0f} {trade_type:<15}")
    
    # 7. 全天分时段分析
    print("\n\n【7. 全天分时段分析】")
    print("=" * 80)
    
    periods = [
        ('09:30:00', '10:00:00', '早盘'),
        ('10:00:00', '11:30:00', '上午'),
        ('13:00:00', '14:00:00', '下午'),
        ('14:00:00', '15:00:00', '尾盘'),
    ]
    
    print(f"{'时段':<15} {'原净额':<15} {'新净额':<15} {'变化':<15}")
    print("-" * 65)
    
    for start, end, name in periods:
        period_old = df[(df['time'] >= start) & (df['time'] < end)]['main_net_amount'].sum()
        period_new = df_new[(df_new['time'] >= start) & (df_new['time'] < end)]['new_main_net'].sum()
        change_pct = (period_new - period_old) / period_old * 100 if period_old != 0 else 0
        
        print(f"{name:<15} {period_old:>14,.0f} {period_new:>14,.0f} {change_pct:>+14.1f}%")
    
    # 8. 结论
    print("\n\n【8. 结论】")
    print("=" * 80)
    
    print(f"\n301396分析结果:")
    print(f"  股票代码: 301396")
    print(f"  全天涨跌幅: {last_change:.2f}%")
    print(f"  走势类型: {trend}")
    print(f"  当前主力净额: {old_total:,.0f} 元 ({old_total/10000:.0f}万)")
    print(f"  新方案净额: {new_total:,.0f} 元 ({new_total/10000:.0f}万)")
    
    if new_total > 0:
        print(f"  方向: 净流入")
    elif new_total < 0:
        print(f"  方向: 净流出")
    else:
        print(f"  方向: 无主力")
    
    print(f"\n新方案效果:")
    reduction = (old_total - new_total) / old_total * 100 if old_total != 0 else 0
    print(f"  净额变化: {reduction:.1f}%")
    print(f"  绝对变化: {old_total - new_total:,.0f} 元")
    
    # 合理性判断
    print(f"\n合理性分析:")
    if trend in ['涨停', '大涨'] and new_total < old_total * 0.5:
        print(f"  股票{trend}，新方案净额大幅降低，可能过度修正")
    elif trend in ['大跌'] and new_total > old_total:
        print(f"  股票{trend}，新方案净额反而增加，可能有问题")
    else:
        print(f"  新方案效果与走势相符")

print("\n" + "=" * 80)
print("分析完成")
