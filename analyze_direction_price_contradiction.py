#!/usr/bin/env python3
"""
深度分析主力方向与股价矛盾的根本原因
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("主力方向与股价矛盾根本原因分析")
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
        
        # 计算变化
        df['price_diff'] = df['price'].diff()
        df['amount_diff'] = df['amount'].diff()
        df['volume_diff'] = df['volume'].diff()
        df['volume_diff'] = df['volume'].diff()
        
        # 1. 基础数据
        print(f"\n【1. 基础数据】")
        print(f"  开盘: {df.iloc[0]['price']:.2f} ({df.iloc[0]['change_pct']:.2f}%)")
        print(f"  收盘: {df.iloc[-1]['price']:.2f} ({df.iloc[-1]['change_pct']:.2f}%)")
        print(f"  主力净额: {df['main_net_amount'].sum():,.0f} 元")
        
        # 判断矛盾类型
        price_change = df.iloc[-1]['change_pct'] - df.iloc[0]['change_pct']
        main_net = df['main_net_amount'].sum()
        
        if price_change > 0 and main_net < 0:
            contradiction = "上涨但主力流出"
        elif price_change < 0 and main_net > 0:
            contradiction = "下跌但主力流入"
        else:
            contradiction = "无矛盾"
        
        print(f"  矛盾类型: {contradiction}")
        
        # 2. 分阶段分析
        print(f"\n【2. 分阶段分析】")
        
        periods = [
            ('09:30:00', '10:00:00', '早盘'),
            ('10:00:00', '11:30:00', '上午'),
            ('13:00:00', '14:00:00', '下午'),
            ('14:00:00', '15:00:00', '尾盘'),
        ]
        
        print(f"{'时段':<10} {'价格变化':<12} {'主力净额':<15} {'矛盾':<15}")
        print("-" * 55)
        
        for start, end, name in periods:
            period_df = df[(df['time'] >= start) & (df['time'] < end)]
            if len(period_df) == 0:
                continue
            
            period_price_change = period_df.iloc[-1]['change_pct'] - period_df.iloc[0]['change_pct']
            period_main_net = period_df['main_net_amount'].sum()
            
            if period_price_change > 0 and period_main_net < 0:
                period_contra = "涨+流出"
            elif period_price_change < 0 and period_main_net > 0:
                period_contra = "跌+流入"
            else:
                period_contra = "一致"
            
            print(f"{name:<10} {period_price_change:>+10.2f}% {period_main_net:>+14,.0f} {period_contra:<15}")
        
        # 3. 矛盾原因分析
        print(f"\n【3. 矛盾原因分析】")
        
        # 3.1 价格变化与主力方向关系
        df['direction'] = np.where(df['price_diff'] > 0, '买入',
                                  np.where(df['price_diff'] < 0, '卖出', '平盘'))
        
        buy_df = df[df['direction'] == '买入']
        sell_df = df[df['direction'] == '卖出']
        
        print(f"\n  方向统计:")
        print(f"    买入: {len(buy_df)} 条, 净额 {buy_df['main_net_amount'].sum():,.0f}")
        print(f"    卖出: {len(sell_df)} 条, 净额 {sell_df['main_net_amount'].sum():,.0f}")
        
        # 3.2 大单分布
        print(f"\n  大单分布 (成交额>100万):")
        big_df = df[df['amount_diff'] > 1000000]
        big_buy = big_df[big_df['direction'] == '买入']
        big_sell = big_df[big_df['direction'] == '卖出']
        
        print(f"    大单买入: {len(big_buy)} 条, 净额 {big_buy['main_net_amount'].sum():,.0f}")
        print(f"    大单卖出: {len(big_sell)} 条, 净额 {big_sell['main_net_amount'].sum():,.0f}")
        
        # 3.3 散户vs主力
        print(f"\n  散户vs主力:")
        retail_df = df[df['amount_diff'] < 300000]  # 散户：30万以下
        main_df = df[df['amount_diff'] >= 300000]  # 主力：30万以上
        
        retail_volume = retail_df['volume_diff'].sum()
        main_volume = main_df['volume_diff'].sum()
        total_volume = df['volume_diff'].sum()
        
        print(f"    散户成交量: {retail_volume:,.0f} ({retail_volume/total_volume*100:.1f}%)")
        print(f"    主力成交量: {main_volume:,.0f} ({main_volume/total_volume*100:.1f}%)")
        
        # 4. 根本原因诊断
        print(f"\n【4. 根本原因诊断】")
        
        # 计算散户推动指数
        retail_buy = retail_df[retail_df['direction'] == '买入']['volume_diff'].sum()
        retail_sell = retail_df[retail_df['direction'] == '卖出']['volume_diff'].sum()
        retail_net = retail_buy - retail_sell
        
        main_buy = main_df[main_df['direction'] == '买入']['volume_diff'].sum()
        main_sell = main_df[main_df['direction'] == 'sell']['volume_diff'].sum()
        main_net = main_buy - main_sell
        
        print(f"\n  散户净流入: {retail_net:,.0f} 股")
        print(f"  主力净流入: {main_net:,.0f} 股")
        
        if abs(retail_net) > abs(main_net) * 2:
            print(f"\n  【诊断】散户推动为主！")
            print(f"    散户净流入是主力的 {retail_net/main_net:.1f} 倍")
            print(f"    股价上涨由散户推动，主力在出货")
        elif main_net < 0 and price_change > 0:
            print(f"\n  【诊断】主力出货，散户接盘！")
            print(f"    主力净流出 {main_net:,.0f} 股")
            print(f"    散户净流入 {retail_net:,.0f} 股")
        
        # 5. 权威修复方案
        print(f"\n【5. 权威修复方案】")
        
        print(f"\n  方案A: 区分散户与主力")
        print(f"    - 散户交易（<30万）：不计入主力净额")
        print(f"    - 主力交易（≥30万）：正常计算")
        
        # 计算方案A效果
        new_main_net = main_df['main_net_amount'].sum()
        print(f"    - 原净额: {main_net:,.0f}")
        print(f"    - 新净额: {new_main_net:,.0f}")
        print(f"    - 变化: {(new_main_net-main_net)/main_net*100:.1f}%")
        
        print(f"\n  方案B: 量价一致性校验")
        print(f"    - 股价上涨时，主力净额应为正")
        print(f"    - 若矛盾，降低该时段权重")
        
        print(f"\n  方案C: 添加散户情绪指标")
        print(f"    - 散户买入占比 > 70%：标记为散户推动")
        print(f"    - 主力净额显示为'散户行情'")

print(f"\n\n{'='*80}")
print("分析完成")
