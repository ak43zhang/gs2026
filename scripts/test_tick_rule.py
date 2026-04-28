#!/usr/bin/env python3
"""
主力净额 - Tick价格变化法
单股测试：000539
"""

import sys
from pathlib import Path
from typing import Tuple
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs"
TABLE_NAME = "monitor_gp_sssj_20260428"
TEST_CODE = "002297"

MAIN_FORCE_CONFIG = {
    'min_amount': 300000,
    'min_volume': 20000,
    'participation_thresholds': {
        'level1': {'amount': 300000,   'ratio': 0.3},
        'level2': {'amount': 500000,   'ratio': 0.5},
        'level3': {'amount': 1000000,  'ratio': 0.8},
        'level4': {'amount': 2000000,  'ratio': 1.0},
    },
}


def calculate_participation_ratio(delta_amount):
    t = MAIN_FORCE_CONFIG['participation_thresholds']
    if delta_amount >= t['level4']['amount']:
        return 1.0
    elif delta_amount >= t['level3']['amount']:
        return t['level3']['ratio'] + (delta_amount - t['level3']['amount']) / \
               (t['level4']['amount'] - t['level3']['amount']) * \
               (t['level4']['ratio'] - t['level3']['ratio'])
    elif delta_amount >= t['level2']['amount']:
        return t['level2']['ratio'] + (delta_amount - t['level2']['amount']) / \
               (t['level3']['amount'] - t['level2']['amount']) * \
               (t['level3']['ratio'] - t['level2']['ratio'])
    elif delta_amount >= t['level1']['amount']:
        return t['level1']['ratio'] + (delta_amount - t['level1']['amount']) / \
               (t['level2']['amount'] - t['level1']['amount']) * \
               (t['level2']['ratio'] - t['level1']['ratio'])
    else:
        return 0.0


def determine_direction(price_diff, last_direction):
    """Tick Rule"""
    if price_diff > 0:
        return 1.0
    elif price_diff < 0:
        return -1.0
    else:
        return last_direction


def calculate_confidence(delta_amount, abs_price_diff, volume_ratio):
    """三因子置信度"""
    # 成交额(40%)
    if delta_amount >= 5_000_000:
        amt_s = 1.0
    elif delta_amount >= 2_000_000:
        amt_s = 0.8
    elif delta_amount >= 1_000_000:
        amt_s = 0.6
    elif delta_amount >= 500_000:
        amt_s = 0.4
    else:
        amt_s = 0.2

    # 价格变化(35%)
    if abs_price_diff >= 0.05:
        prc_s = 1.0
    elif abs_price_diff >= 0.03:
        prc_s = 0.7
    elif abs_price_diff >= 0.01:
        prc_s = 0.4
    else:
        prc_s = 0.1

    # 量能比(25%)
    if volume_ratio >= 10:
        vol_s = 1.0
    elif volume_ratio >= 5:
        vol_s = 0.7
    elif volume_ratio >= 2:
        vol_s = 0.4
    else:
        vol_s = 0.2

    return round(amt_s * 0.40 + prc_s * 0.35 + vol_s * 0.25, 2)


def label_behavior(direction, confidence):
    if confidence >= 0.7:
        prefix = "da"  # 大额
    elif confidence >= 0.4:
        prefix = "zhong"  # 中额
    else:
        prefix = "xiao"  # 小额
    return f"{prefix}_buy" if direction > 0 else f"{prefix}_sell"


def label_behavior_cn(direction, confidence):
    if confidence >= 0.7:
        prefix = "大额"
    elif confidence >= 0.4:
        prefix = "中额"
    else:
        prefix = "小额"
    return f"{prefix}买入" if direction > 0 else f"{prefix}卖出"


def main():
    engine = create_engine(DB_URL)

    # 1. 读取数据
    with engine.connect() as conn:
        df = pd.read_sql(f"""
            SELECT stock_code, short_name, price, volume, amount, change_pct, time
            FROM {TABLE_NAME}
            WHERE stock_code = '{TEST_CODE}'
            ORDER BY time
        """, conn)

    if df.empty:
        print(f"[ERROR] {TEST_CODE} no data")
        return

    stock_name = df['short_name'].iloc[0]
    print(f"=== {TEST_CODE} {stock_name} - Tick Rule ===")
    print(f"Total records: {len(df)}")

    # 2. 数值转换
    for col in ['price', 'volume', 'amount', 'change_pct']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.sort_values('time').reset_index(drop=True)

    # 3. 计算差值
    df['price_diff'] = df['price'].diff().fillna(0)
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)

    median_vol = df['delta_volume'].median()
    if median_vol <= 0:
        median_vol = 20000
    df['volume_ratio'] = df['delta_volume'] / median_vol

    day_high = df['price'].max()
    day_low = df['price'].min()

    print(f"Price range: {day_low:.2f} - {day_high:.2f}")
    print(f"Median delta_volume: {median_vol:,.0f}")
    print()

    # 4. 门槛统计
    mask_amt = df['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']
    mask_vol = df['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume']
    mask_both = mask_amt & mask_vol
    print(f"Above amount threshold (>=30w): {mask_amt.sum()}")
    print(f"Above volume threshold (>=200shou): {mask_vol.sum()}")
    print(f"Above both: {mask_both.sum()}")
    print()

    # 5. 计算主力净额
    df['main_net_amount'] = 0.0
    df['main_behavior'] = ''
    df['main_confidence'] = 0.0

    last_direction = 0.0
    hit_count = 0

    for idx, row in df.iterrows():
        # 更新方向（即使不满足门槛）
        if row['price_diff'] > 0:
            last_direction = 1.0
        elif row['price_diff'] < 0:
            last_direction = -1.0

        # 门槛检查
        if row['delta_amount'] < MAIN_FORCE_CONFIG['min_amount'] or \
           row['delta_volume'] < MAIN_FORCE_CONFIG['min_volume']:
            continue

        # Tick Rule方向
        direction = determine_direction(row['price_diff'], last_direction)

        if direction == 0:
            continue

        # 置信度
        confidence = calculate_confidence(
            row['delta_amount'],
            abs(row['price_diff']),
            row['volume_ratio']
        )

        # 参与系数
        participation = calculate_participation_ratio(row['delta_amount'])

        # 主力净额
        main_net = row['delta_amount'] * direction * participation * confidence

        # 行为标签（用英文避免编码问题）
        behavior = label_behavior(direction, confidence)

        df.at[idx, 'main_net_amount'] = round(main_net, 2)
        df.at[idx, 'main_behavior'] = behavior
        df.at[idx, 'main_confidence'] = round(confidence, 2)
        hit_count += 1

    print(f"Records with main_net_amount != 0: {hit_count}")
    print()

    # 6. 统计分析
    df_main = df[df['main_net_amount'] != 0].copy()

    if df_main.empty:
        print("[INFO] No main force records")
        return

    total_net = df_main['main_net_amount'].sum()
    inflow = df_main[df_main['main_net_amount'] > 0]['main_net_amount'].sum()
    outflow = df_main[df_main['main_net_amount'] < 0]['main_net_amount'].sum()
    buy_count = (df_main['main_net_amount'] > 0).sum()
    sell_count = (df_main['main_net_amount'] < 0).sum()

    print("=== Summary ===")
    print(f"Total main_net: {total_net:>16,.2f}")
    print(f"Inflow (buy):   {inflow:>16,.2f}  ({buy_count} records)")
    print(f"Outflow (sell):  {outflow:>16,.2f}  ({sell_count} records)")
    print()

    # 按行为统计
    print("=== Behavior Distribution ===")
    beh_stats = df_main.groupby('main_behavior').agg(
        count=('main_net_amount', 'count'),
        total=('main_net_amount', 'sum'),
        avg_conf=('main_confidence', 'mean')
    ).reset_index().sort_values('count', ascending=False)
    for _, r in beh_stats.iterrows():
        print(f"  {r['main_behavior']:<15} {int(r['count']):>5} records, total={r['total']:>14,.0f}, avg_conf={r['avg_conf']:.2f}")
    print()

    # 7. 关键时段分析
    print("=== Key Period Analysis ===")
    print()

    # 早盘 9:30-10:00
    early = df_main[(df_main['time'] >= '09:30:00') & (df_main['time'] <= '10:00:00')]
    if not early.empty:
        e_net = early['main_net_amount'].sum()
        e_buy = (early['main_net_amount'] > 0).sum()
        e_sell = (early['main_net_amount'] < 0).sum()
        print(f"[09:30-10:00] net={e_net:>12,.0f}, buy={e_buy}, sell={e_sell}")

    # 下午拉升 13:15-13:25
    pump = df_main[(df_main['time'] >= '13:15:00') & (df_main['time'] <= '13:25:00')]
    if not pump.empty:
        p_net = pump['main_net_amount'].sum()
        p_buy = (pump['main_net_amount'] > 0).sum()
        p_sell = (pump['main_net_amount'] < 0).sum()
        print(f"[13:15-13:25] net={p_net:>12,.0f}, buy={p_buy}, sell={p_sell}")

    # 冲高阶段 14:15-14:19
    rush = df_main[(df_main['time'] >= '14:15:00') & (df_main['time'] <= '14:19:00')]
    if not rush.empty:
        r_net = rush['main_net_amount'].sum()
        r_buy = (rush['main_net_amount'] > 0).sum()
        r_sell = (rush['main_net_amount'] < 0).sum()
        print(f"[14:15-14:19] net={r_net:>12,.0f}, buy={r_buy}, sell={r_sell}  << rush up")

    # 回落阶段 14:19-14:30
    fall = df_main[(df_main['time'] >= '14:19:00') & (df_main['time'] <= '14:30:00')]
    if not fall.empty:
        f_net = fall['main_net_amount'].sum()
        f_buy = (fall['main_net_amount'] > 0).sum()
        f_sell = (fall['main_net_amount'] < 0).sum()
        print(f"[14:19-14:30] net={f_net:>12,.0f}, buy={f_buy}, sell={f_sell}  << fall back")

    print()

    # 8. 冲高回落详细记录（重点验证区间）
    print("=== Detail: 14:17-14:25 (rush + fall) ===")
    detail = df_main[(df_main['time'] >= '14:17:00') & (df_main['time'] <= '14:25:00')]
    if not detail.empty:
        print(f"{'time':<12} {'price':>7} {'p_diff':>7} {'delta_amt':>12} {'direction':>5} {'net_amt':>14} {'behavior':<15} {'conf':>5}")
        print("-" * 90)
        for _, r in detail.iterrows():
            d = "BUY" if r['main_net_amount'] > 0 else "SELL"
            print(f"{r['time']:<12} {r['price']:>7.2f} {r['price_diff']:>+6.2f} "
                  f"{r['delta_amount']:>11,.0f} {d:>5} "
                  f"{r['main_net_amount']:>13,.0f} {r['main_behavior']:<15} {r['main_confidence']:>5.2f}")
    print()

    # 9. price_diff=0的处理统计
    zero_diff = df_main[df['price_diff'] == 0]
    nonzero_diff = df_main[df['price_diff'] != 0]
    print(f"=== price_diff distribution (in main records) ===")
    print(f"price_diff > 0 (direct BUY):  {(df_main['price_diff'] > 0).sum()}")
    print(f"price_diff < 0 (direct SELL): {(df_main['price_diff'] < 0).sum()}")
    print(f"price_diff = 0 (inherited):   {(df_main['price_diff'] == 0).sum()}")
    print()

    # 10. 写入数据库
    print("=== Write to DB ===")
    with engine.connect() as conn:
        # 清除该股旧数据
        conn.execute(text(f"""
            UPDATE {TABLE_NAME}
            SET main_net_amount = 0, main_behavior = '', main_confidence = 0
            WHERE stock_code = '{TEST_CODE}'
        """))
        conn.commit()

        # 写入新结果
        updated = 0
        for _, row in df.iterrows():
            if row['main_net_amount'] != 0 or row['main_behavior']:
                conn.execute(text(f"""
                    UPDATE {TABLE_NAME}
                    SET main_net_amount = {row['main_net_amount']},
                        main_behavior = '{row['main_behavior']}',
                        main_confidence = {row['main_confidence']}
                    WHERE stock_code = '{TEST_CODE}'
                    AND time = '{row['time']}'
                """))
                updated += 1
        conn.commit()
        print(f"[OK] Updated {updated} records")

    # 11. DB验证
    print()
    print("=== DB Verification ===")
    with engine.connect() as conn:
        verify = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount > 0 THEN 1 ELSE 0 END) as buy_cnt,
                SUM(CASE WHEN main_net_amount < 0 THEN 1 ELSE 0 END) as sell_cnt,
                SUM(CASE WHEN main_net_amount > 0 THEN main_net_amount ELSE 0 END) as total_buy,
                SUM(CASE WHEN main_net_amount < 0 THEN main_net_amount ELSE 0 END) as total_sell,
                SUM(main_net_amount) as net
            FROM {TABLE_NAME}
            WHERE stock_code = '{TEST_CODE}'
            AND main_net_amount != 0
        """)).fetchone()
        print(f"DB records with net!=0: {verify[0]}")
        print(f"DB buy:  {verify[1]} records, total={float(verify[3]):>14,.2f}")
        print(f"DB sell: {verify[2]} records, total={float(verify[4]):>14,.2f}")
        print(f"DB net:  {float(verify[5]):>14,.2f}")

    print()
    print("[DONE]")


if __name__ == "__main__":
    main()
