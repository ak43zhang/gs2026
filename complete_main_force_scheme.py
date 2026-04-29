#!/usr/bin/env python3
"""
完整的主力净额计算方案（v2.0）
整合所有讨论点：
1. 排除集合竞价数据
2. 动态散户/主力划分
3. 影响力权重
4. 早盘特殊处理
5. 价格-主力一致性校验
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, time as dt_time
import math

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("完整主力净额计算方案 v2.0")
print("=" * 80)

# 方案配置
CONFIG = {
    'exclude_auction': True,           # 排除集合竞价
    'retail_record_pct': 0.65,         # 散户记录数占比目标
    'retail_amount_pct': 0.15,         # 散户成交额占比目标
    'morning_start': '09:30:00',
    'morning_end': '09:45:00',
    'passive_trade_discount': 0.5,       # 被动交易降权50%
    'direction_validation': True,        # 方向一致性校验
    'influence_weight': True,            # 影响力权重
}

def calculate_influence_weight(amount):
    """影响力权重：对数曲线"""
    if amount < 10000:
        return 0.1
    elif amount < 100000:
        return 0.1 + 0.4 * (math.log10(amount) - 4)
    elif amount < 1000000:
        return 0.5 + 0.3 * (math.log10(amount) - 5)
    elif amount < 10000000:
        return 0.8 + 0.15 * (math.log10(amount) - 6)
    else:
        return 0.95

def determine_trade_type(row, prev_row):
    """判断交易类型"""
    if pd.isna(row['price_diff']):
        return 'first'
    
    price_diff = row['price_diff']
    change_pct = row['change_pct']
    
    # 主动买入：价格上涨时买入
    if price_diff > 0 and change_pct > 0:
        return 'active_buy'
    # 主动卖出：价格下跌时卖出
    elif price_diff < 0 and change_pct < 0:
        return 'active_sell'
    # 被动买入：价格下跌时买入（抄底）
    elif price_diff > 0 and change_pct < -2:
        return 'passive_buy'
    # 被动卖出：价格上涨时卖出（出货）
    elif price_diff < 0 and change_pct > 2:
        return 'passive_sell'
    else:
        return 'normal'

def classify_trade_behavior(main_net, price_change):
    """交易行为标签"""
    if price_change > 0 and main_net > 0:
        return {'type': '主力拉升', 'signal': '看涨'}
    elif price_change > 0 and main_net < 0:
        return {'type': '主力出货', 'signal': '看跌'}
    elif price_change < 0 and main_net > 0:
        return {'type': '主力吸筹', 'signal': '看涨'}
    else:
        return {'type': '主力离场', 'signal': '看跌'}

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
            continue
        
        df['price'] = df['price'].astype(float)
        df['change_pct'] = df['change_pct'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['amount'] = df['amount'].astype(float)
        df['main_net_amount'] = df['main_net_amount'].astype(float)
        
        df['price_diff'] = df['price'].diff()
        df['amount_diff'] = df['amount'].diff()
        
        # 步骤1: 排除集合竞价
        if CONFIG['exclude_auction']:
            df = df[df['time'] >= '09:30:00'].copy()
            print(f"\n步骤1 - 排除集合竞价: 剩余{len(df)}条")
        
        # 步骤2: 动态划分散户/主力
        amounts = sorted(df['amount_diff'].dropna())
        record_threshold_idx = int(len(amounts) * CONFIG['retail_record_pct'])
        record_threshold = amounts[record_threshold_idx]
        
        # 验证成交额占比
        retail_df = df[df['amount_diff'] < record_threshold]
        retail_amount_pct = retail_df['amount_diff'].sum() / df['amount_diff'].sum()
        
        # 如果成交占比过低，调整门槛
        if retail_amount_pct < CONFIG['retail_amount_pct']:
            cumsum = df['amount_diff'].cumsum()
            total = df['amount_diff'].sum()
            target_amount = total * CONFIG['retail_amount_pct']
            amount_threshold_idx = (cumsum >= target_amount).idxmax()
            amount_threshold = df.loc[amount_threshold_idx, 'amount_diff']
            final_threshold = (record_threshold + amount_threshold) / 2
        else:
            final_threshold = record_threshold
        
        df['investor_type'] = df['amount_diff'].apply(
            lambda x: '散户' if x < final_threshold else '主力'
        )
        
        print(f"\n步骤2 - 动态划分:")
        print(f"  门槛: {final_threshold:,.0f}元")
        retail_count = len(df[df['investor_type'] == '散户'])
        main_count = len(df[df['investor_type'] == '主力'])
        print(f"  散户: {retail_count}条 ({retail_count/len(df)*100:.1f}%)")
        print(f"  主力: {main_count}条 ({main_count/len(df)*100:.1f}%)")
        
        # 步骤3: 判断交易类型
        df['trade_type'] = 'normal'
        for idx in range(len(df)):
            if idx == 0:
                df.at[df.index[idx], 'trade_type'] = 'first'
            else:
                row = df.iloc[idx]
                prev_row = df.iloc[idx-1]
                trade_type = determine_trade_type(row, prev_row)
                df.at[df.index[idx], 'trade_type'] = trade_type
        
        # 统计交易类型
        print(f"\n步骤3 - 交易类型分布:")
        for ttype in df['trade_type'].value_counts().index:
            count = len(df[df['trade_type'] == ttype])
            print(f"  {ttype}: {count}条")
        
        # 步骤4: 计算新主力净额
        df['new_main_net'] = 0.0
        
        for idx, row in df.iterrows():
            amount_diff = row['amount_diff']
            price_diff = row['price_diff']
            trade_type = row['trade_type']
            investor_type = row['investor_type']
            time_str = row['time']
            
            if pd.isna(price_diff) or amount_diff <= 0:
                continue
            
            # 方向
            direction = 1 if price_diff > 0 else (-1 if price_diff < 0 else 0)
            
            # 基础主力净额（成交额 * 方向）
            base_main_net = amount_diff * direction
            
            # 影响力权重
            if CONFIG['influence_weight']:
                weight = calculate_influence_weight(amount_diff)
            else:
                weight = 1.0
            
            # 早盘被动交易降权
            if CONFIG['morning_start'] <= time_str < CONFIG['morning_end']:
                if trade_type in ['passive_buy', 'passive_sell']:
                    weight *= CONFIG['passive_trade_discount']
            
            # 散户降权
            if investor_type == '散户':
                weight *= 0.2  # 散户影响力降至20%
            
            df.at[idx, 'new_main_net'] = base_main_net * weight
        
        # 步骤5: 方向一致性校验
        if CONFIG['direction_validation']:
            price_change = df.iloc[-1]['change_pct'] - df.iloc[0]['change_pct']
            main_net_total = df['new_main_net'].sum()
            
            # 如果矛盾，添加标记
            if (price_change > 0 and main_net_total < 0) or (price_change < 0 and main_net_total > 0):
                behavior = classify_trade_behavior(main_net_total, price_change)
                print(f"\n步骤5 - 行为标签: {behavior['type']} ({behavior['signal']})")
            else:
                print(f"\n步骤5 - 方向一致: {'看涨' if main_net_total > 0 else '看跌'}")
        
        # 结果对比
        old_total = df['main_net_amount'].sum()
        new_total = df['new_main_net'].sum()
        
        print(f"\n{'='*80}")
        print(f"结果对比:")
        print(f"  原主力净额: {old_total:,.0f}元 ({old_total/10000:.0f}万)")
        print(f"  新主力净额: {new_total:,.0f}元 ({new_total/10000:.0f}万)")
        print(f"  变化: {(new_total-old_total)/old_total*100:+.1f}%")
        print(f"{'='*80}")

print(f"\n\n{'='*80}")
print("方案说明:")
print("="*80)
print("""
【完整方案 v2.0】

1. 数据预处理
   - 排除集合竞价数据（09:30:00前）
   - 计算价格/成交额变化

2. 动态划分散户/主力
   - 目标：散户记录数占比65% + 成交额占比15%
   - 门槛根据每只股票动态计算

3. 交易类型判断
   - active_buy: 价格上涨时买入
   - active_sell: 价格下跌时卖出
   - passive_buy: 大跌中买入（抄底）
   - passive_sell: 大涨中卖出（出货）

4. 影响力权重
   - 对数曲线：小单0.1 → 大单0.95
   - 避免大单过度主导

5. 早盘特殊处理
   - 09:30-09:45期间
   - 被动交易降权50%

6. 散户降权
   - 散户影响力降至20%
   - 主力计算更聚焦

7. 行为标签
   - 主力拉升/出货/吸筹/离场
   - 添加信号解读
""")
print("分析完成")
