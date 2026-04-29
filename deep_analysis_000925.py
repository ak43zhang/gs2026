#!/usr/bin/env python3
"""
深度分析000925主力净额计算
对比其他软件（-7000w）vs 我们的计算（+2亿）
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("000925 主力净额深度分析")
print("=" * 80)
print("\n对比：其他软件显示 -7000w vs 我们计算 +2亿")
print("差异：2.7亿！需要排查原因")
print()

with engine.connect() as conn:
    # 1. 获取原始数据
    print("【1. 原始数据检查】")
    print("-" * 80)
    
    df = pd.read_sql("""
        SELECT 
            time, 
            price, 
            change_pct,
            volume,
            amount,
            main_net_amount,
            main_behavior,
            main_confidence,
            cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time
    """, conn)
    
    print(f"总记录数: {len(df)}")
    print(f"\n数据样例（前5条）:")
    print(df.head().to_string(index=False))
    
    # 2. 计算基础统计
    print("\n\n【2. 基础统计】")
    print("-" * 80)
    
    df['price'] = df['price'].astype(float)
    df['change_pct'] = df['change_pct'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df['amount'] = df['amount'].astype(float)
    df['main_net_amount'] = df['main_net_amount'].astype(float)
    
    # 计算价格变化
    df['price_diff'] = df['price'].diff()
    df['volume_diff'] = df['volume'].diff()
    df['amount_diff'] = df['amount'].diff()
    
    print(f"价格范围: {df['price'].min():.2f} ~ {df['price'].max():.2f}")
    print(f"涨跌幅范围: {df['change_pct'].min():.2f}% ~ {df['change_pct'].max():.2f}%")
    print(f"成交量范围: {df['volume'].min():.0f} ~ {df['volume'].max():.0f}")
    print(f"成交额范围: {df['amount'].min():.0f} ~ {df['amount'].max():.0f}")
    
    # 3. 检查我们的主力净额计算
    print("\n\n【3. 我们的主力净额统计】")
    print("-" * 80)
    
    total_main_net = df['main_net_amount'].sum()
    positive_main_net = df[df['main_net_amount'] > 0]['main_net_amount'].sum()
    negative_main_net = df[df['main_net_amount'] < 0]['main_net_amount'].sum()
    
    print(f"主力净额总和: {total_main_net:,.0f} 元 ({total_main_net/10000:.1f}万)")
    print(f"流入总额: {positive_main_net:,.0f} 元 ({positive_main_net/10000:.1f}万)")
    print(f"流出总额: {negative_main_net:,.0f} 元 ({negative_main_net/10000:.1f}万)")
    print(f"净流入次数: {len(df[df['main_net_amount'] > 0])}")
    print(f"净流出次数: {len(df[df['main_net_amount'] < 0])}")
    
    # 4. 检查大单方向
    print("\n\n【4. 大单分析（>100万）】")
    print("-" * 80)
    
    big_orders = df[df['amount_diff'].abs() > 1000000].copy()
    print(f"大单记录数: {len(big_orders)}")
    
    if len(big_orders) > 0:
        big_orders['direction'] = np.where(big_orders['price_diff'] > 0, '买入', 
                                           np.where(big_orders['price_diff'] < 0, '卖出', '平'))
        
        buy_big = big_orders[big_orders['direction'] == '买入']
        sell_big = big_orders[big_orders['direction'] == '卖出']
        
        print(f"\n大单买入: {len(buy_big)} 笔, 总额 {buy_big['amount_diff'].sum():,.0f} 元")
        print(f"大单卖出: {len(sell_big)} 笔, 总额 {sell_big['amount_diff'].sum():,.0f} 元")
        
        print(f"\n大单净额: {(buy_big['amount_diff'].sum() - sell_big['amount_diff'].sum()):,.0f} 元")
    
    # 5. 检查可能的问题：参与系数
    print("\n\n【5. 参与系数分析】")
    print("-" * 80)
    
    # 模拟计算参与系数
    def calc_participation(delta_amount):
        if delta_amount >= 2000000:
            return 1.0
        elif delta_amount >= 1000000:
            return 0.8
        elif delta_amount >= 500000:
            return 0.6
        elif delta_amount >= 300000:
            return 0.4
        else:
            return 0.0
    
    df['participation'] = df['amount_diff'].apply(calc_participation)
    
    print("参与系数分布:")
    print(df['participation'].value_counts().sort_index(ascending=False).to_string())
    
    # 6. 检查可能的问题：方向判断
    print("\n\n【6. 方向判断分析】")
    print("-" * 80)
    
    df['our_direction'] = np.where(df['price_diff'] > 0, 1, 
                                   np.where(df['price_diff'] < 0, -1, 0))
    
    direction_stats = df.groupby('our_direction').agg({
        'main_net_amount': ['count', 'sum'],
        'amount_diff': 'sum'
    }).reset_index()
    
    print("我们的方向判断统计:")
    print(f"{'方向':<10} {'记录数':<10} {'主力净额':<15} {'成交额变化':<15}")
    print("-" * 80)
    for _, row in direction_stats.iterrows():
        direction = row['our_direction']
        count = row[('main_net_amount', 'count')]
        main_net = row[('main_net_amount', 'sum')]
        amount = row[('amount_diff', 'sum')]
        
        if direction == 1:
            direction_str = '买入(+1)'
        elif direction == -1:
            direction_str = '卖出(-1)'
        else:
            direction_str = '平盘(0)'
        print(f"{direction_str:<10} {count:<10} {main_net:<15.0f} {amount:<15.0f}")
    
    # 7. 关键发现：检查早盘数据
    print("\n\n【7. 早盘数据检查（9:30-10:00）】")
    print("-" * 80)
    
    morning = df[df['time'] <= '10:00:00'].copy()
    print(f"早盘记录数: {len(morning)}")
    print(f"早盘主力净额: {morning['main_net_amount'].sum():,.0f} 元")
    print(f"早盘价格变化: {morning['price'].iloc[0]:.2f} -> {morning['price'].iloc[-1]:.2f}")
    
    # 检查是否有异常大单
    big_morning = morning[morning['amount_diff'].abs() > 5000000]
    print(f"\n早盘大单（>500万）: {len(big_morning)} 笔")
    if len(big_morning) > 0:
        print("\n大单详情:")
        print(big_morning[['time', 'price', 'price_diff', 'amount_diff', 'main_net_amount', 'our_direction']].to_string(index=False))
    
    # 8. 模拟其他软件的算法
    print("\n\n【8. 模拟其他软件算法】")
    print("-" * 80)
    
    # 算法A：只看大单（>100万）
    big_only = df[df['amount_diff'].abs() > 1000000]
    big_only_net = (big_only[big_only['our_direction'] == 1]['amount_diff'].sum() - 
                   big_only[big_only['our_direction'] == -1]['amount_diff'].sum())
    print(f"算法A（只看大单>100万）: {big_only_net:,.0f} 元")
    
    # 算法B：固定参与系数0.5
    fixed_participation = df['amount_diff'] * 0.5 * df['our_direction']
    print(f"算法B（固定参与系数0.5）: {fixed_participation.sum():,.0f} 元")
    
    # 算法C：只看涨跌幅变化
    df['change_diff'] = df['change_pct'].diff()
    change_direction = np.where(df['change_diff'] > 0, 1, 
                              np.where(df['change_diff'] < 0, -1, 0))
    change_based = df['amount_diff'] * 0.5 * change_direction
    print(f"算法C（基于涨跌幅变化）: {change_based.sum():,.0f} 元")
    
    # 算法D：只看尾盘（14:30-15:00）
    afternoon = df[df['time'] >= '14:30:00']
    afternoon_net = afternoon['main_net_amount'].sum()
    print(f"算法D（只看尾盘）: {afternoon_net:,.0f} 元")
    
    # 9. 可能的问题点
    print("\n\n【9. 可能的问题点】")
    print("-" * 80)
    
    # 检查价格diff异常
    df['price_diff_pct'] = df['price_diff'] / df['price'].shift(1) * 100
    abnormal_diff = df[(df['price_diff_pct'].abs() > 1) & (df['main_net_amount'] != 0)]
    print(f"价格变化>1%且有主力净额的记录: {len(abnormal_diff)} 条")
    
    # 检查连续同方向
    df['direction_change'] = df['our_direction'] != df['our_direction'].shift(1)
    direction_changes = df['direction_change'].sum()
    print(f"方向变化次数: {direction_changes} / {len(df)} ({direction_changes/len(df)*100:.1f}%)")
    
    # 10. 结论
    print("\n\n【10. 分析结论】")
    print("=" * 80)
    
    print("\n我们的计算结果:")
    print(f"  主力净额总和: {total_main_net:,.0f} 元 (+{total_main_net/10000:.0f}万)")
    
    print("\n其他软件显示: -7000万")
    print("\n差异分析:")
    print(f"  1. 我们的净流入: +{positive_main_net/10000:.0f}万")
    print(f"  2. 我们的净流出: {negative_main_net/10000:.0f}万")
    print(f"  3. 净流入比流出多: {(positive_main_net + negative_main_net)/10000:.0f}万")
    print(f"  4. 差异原因: 我们的参与系数可能过高，或方向判断有误")
    
    print("\n可能的问题:")
    print("  1. 【高】参与系数设置过高（最高1.0）")
    print("  2. 【高】价格diff=0时继承上一方向，可能累积误差")
    print("  3. 【中】早盘低开时大量买入信号，但可能是恐慌盘")
    print("  4. 【低】大单识别阈值过低（30万）")
    
    print("\n建议检查:")
    print("  1. 降低参与系数上限（1.0 -> 0.5）")
    print("  2. 价格diff=0时不继承方向，设为0")
    print("  3. 添加价格位置权重（低位买入权重高，高位买入权重低）")
    print("  4. 提高大单阈值（30万 -> 100万）")

print("\n" + "=" * 80)
print("分析完成")
