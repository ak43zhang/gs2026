#!/usr/bin/env python3
"""
深度分析三个核心问题：
1. 第一笔交易方向判定
2. 为什么买入次数少但净额为正
3. 参与系数的影响
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("000925 核心问题深度分析")
print("=" * 80)

with engine.connect() as conn:
    # 获取详细数据
    df = pd.read_sql("""
        SELECT 
            time, 
            price, 
            change_pct,
            volume,
            amount,
            main_net_amount,
            main_behavior,
            main_confidence
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
    df['change_diff'] = df['change_pct'].diff()
    
    # 问题1：第一笔交易分析
    print("\n【问题1】第一笔交易方向判定")
    print("=" * 80)
    
    # 找出最早的几笔交易
    first_10 = df.head(10).copy()
    
    print("\n最早10笔交易:")
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'价格变化':<10} {'成交额变化':<15} {'主力净额':<15} {'行为':<15}")
    print("-" * 110)
    
    for idx, row in first_10.iterrows():
        time_str = row['time']
        price = row['price']
        change_pct = row['change_pct']
        price_diff = row['price_diff']
        amount_diff = row['amount_diff']
        main_net = row['main_net_amount']
        behavior = row['main_behavior']
        
        # 显示方向判断逻辑
        if pd.isna(price_diff):
            direction_logic = "首笔，无对比"
        elif price_diff > 0:
            direction_logic = "price_diff>0 → 买入"
        elif price_diff < 0:
            direction_logic = "price_diff<0 → 卖出"
        else:
            direction_logic = "price_diff=0 → 继承"
        
        print(f"{time_str:<12} {price:<8.2f} {change_pct:<10.2f} {price_diff:<10.2f} {amount_diff:<15.0f} {main_net:<15.0f} {direction_logic:<15}")
    
    # 分析第一笔的问题
    print("\n【第一笔交易详细分析】")
    first_row = df.iloc[0]
    second_row = df.iloc[1] if len(df) > 1 else None
    
    print(f"第一笔时间: {first_row['time']}")
    print(f"第一笔价格: {first_row['price']}")
    print(f"第一笔涨跌幅: {first_row['change_pct']}%")
    print(f"第一笔成交额: {first_row['amount']:,.0f}")
    print(f"第一笔主力净额: {first_row['main_net_amount']:,.0f}")
    print(f"第一笔行为: {first_row['main_behavior']}")
    
    if second_row is not None:
        print(f"\n第二笔时间: {second_row['time']}")
        print(f"第二笔价格: {second_row['price']}")
        print(f"第二笔涨跌幅: {second_row['change_pct']}%")
        print(f"价格变化: {second_row['price'] - first_row['price']:.2f}")
        print(f"涨跌幅变化: {second_row['change_pct'] - first_row['change_pct']:.2f}%")
    
    print("\n【问题】第一笔为什么有主力净额？")
    print("- 第一笔没有上一笔对比，price_diff=NaN")
    print("- 但change_pct=1.58% > 0，可能被判定为买入")
    print("- 实际上这是集合竞价后的第一笔，不应有方向")
    
    # 问题2：买入次数少但净额为正
    print("\n\n【问题2】为什么买入次数少但净额为正？")
    print("=" * 80)
    
    # 统计买入vs卖出的金额差异
    df['direction'] = np.where(df['price_diff'] > 0, '买入',
                              np.where(df['price_diff'] < 0, '卖出', '平盘'))
    
    buy_records = df[df['direction'] == '买入']
    sell_records = df[df['direction'] == '卖出']
    flat_records = df[df['direction'] == '平盘']
    
    print(f"\n方向统计:")
    print(f"买入记录: {len(buy_records)} 条 ({len(buy_records)/len(df)*100:.1f}%)")
    print(f"卖出记录: {len(sell_records)} 条 ({len(sell_records)/len(df)*100:.1f}%)")
    print(f"平盘记录: {len(flat_records)} 条 ({len(flat_records)/len(df)*100:.1f}%)")
    
    print(f"\n金额统计:")
    print(f"买入总额: {buy_records['amount_diff'].sum():,.0f} 元")
    print(f"卖出总额: {sell_records['amount_diff'].sum():,.0f} 元")
    print(f"买入平均: {buy_records['amount_diff'].mean():,.0f} 元/笔")
    print(f"卖出平均: {sell_records['amount_diff'].mean():,.0f} 元/笔")
    
    print(f"\n主力净额统计:")
    print(f"买入主力净额: {buy_records['main_net_amount'].sum():,.0f} 元")
    print(f"卖出主力净额: {sell_records['main_net_amount'].sum():,.0f} 元")
    print(f"买入平均主力净额: {buy_records['main_net_amount'].mean():,.0f} 元/笔")
    print(f"卖出平均主力净额: {sell_records['main_net_amount'].mean():,.0f} 元/笔")
    
    # 关键发现：买入单笔金额更大
    print("\n【关键发现】")
    buy_avg = buy_records['amount_diff'].mean()
    sell_avg = sell_records['amount_diff'].mean()
    print(f"买入单笔平均成交额: {buy_avg:,.0f} 元")
    print(f"卖出单笔平均成交额: {sell_avg:,.0f} 元")
    print(f"买入/卖出金额比: {buy_avg/sell_avg:.2f}")
    
    if buy_avg > sell_avg:
        print(f"\n【解释】虽然买入次数少，但单笔买入金额比卖出高 {buy_avg/sell_avg:.2f} 倍！")
        print("这导致总流入 > 总流出，净额为正")
    
    # 问题3：参与系数的影响
    print("\n\n【问题3】参与系数的影响")
    print("=" * 80)
    
    # 计算不同参与系数下的净额
    def calc_with_participation(participation_dict):
        """使用不同的参与系数计算主力净额"""
        result = []
        for _, row in df.iterrows():
            amount_diff = row['amount_diff']
            direction = 1 if row['price_diff'] > 0 else (-1 if row['price_diff'] < 0 else 0)
            
            # 根据金额确定参与系数
            if amount_diff >= 2000000:
                p = participation_dict['level4']
            elif amount_diff >= 1000000:
                p = participation_dict['level3']
            elif amount_diff >= 500000:
                p = participation_dict['level2']
            elif amount_diff >= 300000:
                p = participation_dict['level1']
            else:
                p = 0
            
            main_net = amount_diff * p * direction
            result.append(main_net)
        
        return sum(result)
    
    # 当前系数
    current = {'level1': 0.4, 'level2': 0.6, 'level3': 0.8, 'level4': 1.0}
    current_total = calc_with_participation(current)
    
    # 降低50%
    half = {'level1': 0.2, 'level2': 0.3, 'level3': 0.4, 'level4': 0.5}
    half_total = calc_with_participation(half)
    
    # 降低70%
    low = {'level1': 0.12, 'level2': 0.18, 'level3': 0.24, 'level4': 0.3}
    low_total = calc_with_participation(low)
    
    # 固定系数
    fixed = {'level1': 0.3, 'level2': 0.3, 'level3': 0.3, 'level4': 0.3}
    fixed_total = calc_with_participation(fixed)
    
    print(f"\n不同参与系数下的主力净额:")
    print(f"当前系数: {current_total:,.0f} 元 (+{current_total/10000:.0f}万)")
    print(f"降低50%:  {half_total:,.0f} 元 ({half_total/10000:.0f}万)")
    print(f"降低70%:  {low_total:,.0f} 元 ({low_total/10000:.0f}万)")
    print(f"固定0.3:  {fixed_total:,.0f} 元 ({fixed_total/10000:.0f}万)")
    print(f"目标:     -70,000,000 元 (-7000万)")
    
    # 找出最接近的
    targets = [current_total, half_total, low_total, fixed_total]
    closest = min(targets, key=lambda x: abs(x - (-70000000)))
    print(f"\n最接近目标的方案: {closest:,.0f} 元")
    
    # 附加分析：按时间段分析
    print("\n\n【附加分析】按时间段分析")
    print("=" * 80)
    
    periods = [
        ('09:30:00', '10:00:00', '早盘'),
        ('10:00:00', '11:30:00', '上午'),
        ('13:00:00', '14:00:00', '下午前半'),
        ('14:00:00', '15:00:00', '尾盘'),
    ]
    
    print(f"{'时间段':<15} {'买入笔数':<10} {'卖出笔数':<10} {'买入金额':<15} {'卖出金额':<15} {'净额':<15}")
    print("-" * 95)
    
    for start, end, name in periods:
        period_df = df[(df['time'] >= start) & (df['time'] < end)]
        
        if len(period_df) == 0:
            continue
        
        period_buy = period_df[period_df['direction'] == '买入']
        period_sell = period_df[period_df['direction'] == '卖出']
        
        buy_count = len(period_buy)
        sell_count = len(period_sell)
        buy_amount = period_buy['main_net_amount'].sum()
        sell_amount = period_sell['main_net_amount'].sum()
        net = buy_amount + sell_amount  # sell是负数
        
        print(f"{name:<15} {buy_count:<10} {sell_count:<10} {buy_amount:<15.0f} {sell_amount:<15.0f} {net:<15.0f}")
    
    # 最终结论
    print("\n\n【最终结论】")
    print("=" * 80)
    
    print("\n问题1（第一笔方向）:")
    print("- 第一笔不应有方向，因为没有上一笔对比")
    print("- 当前可能用change_pct>0判定为买入，这是错误的")
    print("- 修复：第一笔主力净额设为0")
    
    print("\n问题2（买入次数少但净额为正）:")
    print(f"- 买入次数: {len(buy_records)}，卖出次数: {len(sell_records)}")
    print(f"- 但买入单笔平均: {buy_avg:,.0f}元，卖出单笔平均: {sell_avg:,.0f}元")
    print(f"- 买入金额是卖出的 {buy_avg/sell_avg:.2f} 倍！")
    print("- 这说明大单主要在买入方向")
    
    print("\n问题3（参与系数）:")
    print(f"- 当前系数导致净额: +{current_total/10000:.0f}万")
    print(f"- 需要降低到: -7000万")
    print(f"- 建议系数: 0.12-0.3（当前0.4-1.0的30%）")

print("\n" + "=" * 80)
print("分析完成")
