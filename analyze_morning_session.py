#!/usr/bin/env python3
"""
深度分析早盘数据，找出更合理的方案
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("早盘数据深度分析")
print("=" * 80)

with engine.connect() as conn:
    # 获取全天数据
    df = pd.read_sql("""
        SELECT 
            time, 
            price, 
            change_pct,
            volume,
            amount,
            main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time
    """, conn)
    
    df['price'] = df['price'].astype(float)
    df['change_pct'] = df['change_pct'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['amount'] = df['amount'].astype(float)
    df['main_net_amount'] = df['main_net_amount'].astype(float)
    
    # 计算变化量
    df['price_diff'] = df['price'].diff()
    df['volume_diff'] = df['volume'].diff()
    df['amount_diff'] = df['amount'].diff()
    
    # 按时间段分析
    print("\n【1. 全天各时段成交量对比】")
    print("=" * 80)
    
    periods = [
        ('09:30:00', '10:00:00', '早盘(9:30-10:00)'),
        ('10:00:00', '11:30:00', '上午(10:00-11:30)'),
        ('13:00:00', '14:00:00', '下午(13:00-14:00)'),
        ('14:00:00', '15:00:00', '尾盘(14:00-15:00)'),
    ]
    
    print(f"{'时段':<20} {'记录数':<10} {'成交量':<15} {'成交额':<15} {'主力净额':<15}")
    print("-" * 80)
    
    for start, end, name in periods:
        period_df = df[(df['time'] >= start) & (df['time'] < end)]
        
        if len(period_df) == 0:
            continue
        
        count = len(period_df)
        volume = period_df['volume_diff'].sum()
        amount = period_df['amount_diff'].sum()
        main_net = period_df['main_net_amount'].sum()
        
        print(f"{name:<20} {count:<10} {volume:<15.0f} {amount:<15.0f} {main_net:<15.0f}")
    
    # 早盘详细分析
    print("\n\n【2. 早盘(9:30-10:00)详细分析】")
    print("=" * 80)
    
    morning = df[(df['time'] >= '09:30:00') & (df['time'] < '10:00:00')].copy()
    
    print(f"早盘记录数: {len(morning)} ({len(morning)/len(df)*100:.1f}% of 全天)")
    print(f"早盘成交量: {morning['volume_diff'].sum():,.0f} ({morning['volume_diff'].sum()/df['volume_diff'].sum()*100:.1f}% of 全天)")
    print(f"早盘成交额: {morning['amount_diff'].sum():,.0f} ({morning['amount_diff'].sum()/df['amount_diff'].sum()*100:.1f}% of 全天)")
    print(f"早盘主力净额: {morning['main_net_amount'].sum():,.0f} ({morning['main_net_amount'].sum()/df['main_net_amount'].sum()*100:.1f}% of 全天)")
    
    # 早盘价格走势
    print(f"\n早盘价格走势:")
    print(f"  开盘: {morning.iloc[0]['price']:.2f}")
    print(f"  最高: {morning['price'].max():.2f}")
    print(f"  最低: {morning['price'].min():.2f}")
    print(f"  收盘: {morning.iloc[-1]['price']:.2f}")
    print(f"  涨跌: {morning.iloc[-1]['price'] - morning.iloc[0]['price']:.2f}")
    
    # 早盘主力行为分析
    morning['direction'] = np.where(morning['price_diff'] > 0, '买入',
                                   np.where(morning['price_diff'] < 0, '卖出', '平盘'))
    
    morning_buy = morning[morning['direction'] == '买入']
    morning_sell = morning[morning['direction'] == '卖出']
    
    print(f"\n早盘主力行为:")
    print(f"  买入次数: {len(morning_buy)} ({len(morning_buy)/len(morning)*100:.1f}%)")
    print(f"  卖出次数: {len(morning_sell)} ({len(morning_sell)/len(morning)*100:.1f}%)")
    print(f"  买入净额: {morning_buy['main_net_amount'].sum():,.0f}")
    print(f"  卖出净额: {morning_sell['main_net_amount'].sum():,.0f}")
    print(f"  早盘净额: {morning['main_net_amount'].sum():,.0f}")
    
    # 关键发现：早盘前5分钟
    print("\n\n【3. 早盘前5分钟(9:30-9:35)关键分析】")
    print("=" * 80)
    
    first_5min = df[(df['time'] >= '09:30:00') & (df['time'] < '09:35:00')].copy()
    
    print(f"前5分钟记录数: {len(first_5min)}")
    print(f"前5分钟成交额: {first_5min['amount_diff'].sum():,.0f}")
    print(f"前5分钟主力净额: {first_5min['main_net_amount'].sum():,.0f}")
    print(f"前5分钟占早盘比例: {first_5min['main_net_amount'].sum()/morning['main_net_amount'].sum()*100:.1f}%")
    
    # 逐笔分析前5分钟
    print(f"\n前5分钟逐笔分析:")
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'价格变化':<10} {'成交额变化':<15} {'主力净额':<15} {'累计净额':<15}")
    print("-" * 100)
    
    cumulative = 0
    for idx, row in first_5min.iterrows():
        cumulative += row['main_net_amount']
        print(f"{row['time']:<12} {row['price']:<8.2f} {row['change_pct']:<10.2f} {row['price_diff']:<10.2f} {row['amount_diff']:<15.0f} {row['main_net_amount']:<15.0f} {cumulative:<15.0f}")
    
    # 发现问题：第一笔和第二笔
    print("\n【关键发现】")
    if len(first_5min) >= 2:
        first = first_5min.iloc[0]
        second = first_5min.iloc[1]
        
        print(f"第一笔(09:26:42): 价格{first['price']:.2f}, 主力净额{first['main_net_amount']:,.0f}")
        print(f"  -> 这是集合竞价数据，不应计算主力净额")
        print()
        print(f"第二笔(09:30:03): 价格{second['price']:.2f}, 涨跌幅{second['change_pct']:.2f}%")
        print(f"  -> 价格从{first['price']:.2f}→{second['price']:.2f}, 变化+{second['price']-first['price']:.2f}")
        print(f"  -> 被判定为买入，主力净额+{second['main_net_amount']:,.0f}")
        print(f"  -> 但紧接着价格大跌到{first_5min.iloc[-1]['price']:.2f}")
        print()
        print(f"【结论】第二笔的+{second['main_net_amount']:,.0f}是误判！")
        print(f"  这是高开后的瞬间，不应算主力买入")
    
    # 4. 问题根源分析
    print("\n\n【4. 问题根源分析】")
    print("=" * 80)
    
    print("\n问题1: 集合竞价数据混入")
    print("- 09:26:42 是集合竞价数据，不应参与计算")
    print("- 但09:30:03与之对比，产生错误方向")
    
    print("\n问题2: 高开瞬间误判")
    print("- 09:30:03 高开+0.06元，被判定为买入")
    print("- 但实际上是前收盘价→开盘价的延续")
    print("- 不应与集合竞价对比")
    
    print("\n问题3: 早盘大单方向")
    print("- 早盘大单主要在买入方向")
    print("- 但价格实际在下跌")
    print("- 说明大单可能是'被动买入'（承接抛压）")
    
    # 5. 替代方案分析
    print("\n\n【5. 替代方案分析】")
    print("=" * 80)
    
    print("\n方案A: 排除集合竞价数据")
    print("- 从09:30:00开始计算，排除09:26:42")
    print("- 09:30:00作为第一笔，无方向")
    
    # 计算排除后的效果
    df_excluded = df[df['time'] >= '09:30:00'].copy()
    excluded_main_net = df_excluded['main_net_amount'].sum()
    print(f"- 预期效果: 净额从{df['main_net_amount'].sum():,.0f} → {excluded_main_net:,.0f}")
    
    print("\n方案B: 早盘使用特殊逻辑")
    print("- 09:30:00-09:35:00 使用涨跌幅变化判断，而非价格变化")
    print("- 或者使用更大的对比窗口（如前1分钟）")
    
    print("\n方案C: 区分主动/被动交易")
    print("- 价格下跌时的买入 = 被动承接（权重降低）")
    print("- 价格上涨时的买入 = 主动拉升（权重正常）")
    
    # 计算方案C的效果
    df_c = df.copy()
    df_c['price_trend'] = np.where(df_c['change_pct'] < df_c['change_pct'].shift(1), '下跌', 
                                  np.where(df_c['change_pct'] > df_c['change_pct'].shift(1), '上涨', '平'))
    
    # 早盘被动买入降权
    morning_mask = (df_c['time'] >= '09:30:00') & (df_c['time'] < '09:35:00')
    passive_buy_mask = morning_mask & (df_c['price_diff'] > 0) & (df_c['change_pct'] < 0)
    
    df_c.loc[passive_buy_mask, 'main_net_amount'] *= 0.2  # 降权80%
    
    adjusted_main_net = df_c['main_net_amount'].sum()
    print(f"- 预期效果: 净额从{df['main_net_amount'].sum():,.0f} → {adjusted_main_net:,.0f}")
    
    # 6. 推荐方案
    print("\n\n【6. 推荐方案】")
    print("=" * 80)
    
    print("\n核心问题: 不是早盘权重问题，而是第一笔对比基准错误！")
    print()
    print("推荐方案: 方案A + 方案C 组合")
    print()
    print("1. 排除集合竞价数据（09:26:42等）")
    print("   - 从09:30:00开始计算")
    print("   - 09:30:00作为第一笔，无方向，主力净额=0")
    print()
    print("2. 早盘被动交易降权")
    print("   - 09:30:00-09:45:00期间")
    print("   - 价格下跌时的买入：权重0.2")
    print("   - 价格上涨时的买入：权重1.0")
    print("   - 卖出方向不变")
    print()
    print("3. 提高大单门槛（全局）")
    print("   - 100万以下：不参与系数=0")
    print("   - 100-500万：系数0.15")
    print("   - 500万以上：系数0.25")
    print()
    
    # 计算最终效果
    df_final = df[df['time'] >= '09:30:00'].copy()
    
    # 早盘被动买入降权
    morning_mask = (df_final['time'] >= '09:30:00') & (df_final['time'] < '09:45:00')
    passive_buy_mask = morning_mask & (df_final['price_diff'] > 0) & (df_final['change_pct'] < 0)
    
    # 同时降低参与系数
    def adjust_participation(amount, is_morning_passive):
        if amount < 1000000:
            return 0
        elif amount < 5000000:
            base = 0.15
        else:
            base = 0.25
        
        if is_morning_passive:
            return base * 0.2  # 再降权80%
        return base
    
    # 简化计算：整体降权
    df_final.loc[passive_buy_mask, 'main_net_amount'] *= 0.2
    df_final['main_net_amount'] *= 0.3  # 全局降权
    
    final_main_net = df_final['main_net_amount'].sum()
    print(f"\n最终预期效果:")
    print(f"  当前: {df['main_net_amount'].sum():,.0f} 元 (+{df['main_net_amount'].sum()/10000:.0f}万)")
    print(f"  调整后: {final_main_net:,.0f} 元 ({final_main_net/10000:.0f}万)")
    print(f"  目标: -70,000,000 元 (-7000万)")

print("\n" + "=" * 80)
print("分析完成")
