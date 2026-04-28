#!/usr/bin/env python3
"""
单股测试脚本 - 验证主力净额计算逻辑
目标：000539
"""

import sys
from pathlib import Path
from datetime import time as dt_time
from typing import Tuple
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs"
TABLE_NAME = "monitor_gp_sssj_20260428"
TEST_CODE = "000539"

MAIN_FORCE_CONFIG = {
    'min_amount': 300000,
    'min_volume': 20000,
    'participation_thresholds': {
        'level1': {'amount': 300000, 'ratio': 0.3},
        'level2': {'amount': 500000, 'ratio': 0.5},
        'level3': {'amount': 1000000, 'ratio': 0.8},
        'level4': {'amount': 2000000, 'ratio': 1.0},
    },
}


def calculate_participation_ratio(delta_amount: float) -> float:
    thresholds = MAIN_FORCE_CONFIG['participation_thresholds']
    if delta_amount >= thresholds['level4']['amount']:
        return 1.0
    elif delta_amount >= thresholds['level3']['amount']:
        return thresholds['level3']['ratio'] + (delta_amount - thresholds['level3']['amount']) / \
               (thresholds['level4']['amount'] - thresholds['level3']['amount']) * \
               (thresholds['level4']['ratio'] - thresholds['level3']['ratio'])
    elif delta_amount >= thresholds['level2']['amount']:
        return thresholds['level2']['ratio'] + (delta_amount - thresholds['level2']['amount']) / \
               (thresholds['level3']['amount'] - thresholds['level2']['amount']) * \
               (thresholds['level3']['ratio'] - thresholds['level2']['ratio'])
    elif delta_amount >= thresholds['level1']['amount']:
        return thresholds['level1']['ratio'] + (delta_amount - thresholds['level1']['amount']) / \
               (thresholds['level2']['amount'] - thresholds['level1']['amount']) * \
               (thresholds['level2']['ratio'] - thresholds['level1']['ratio'])
    else:
        return 0.0


def classify_behavior(price_position, price_change_pct, volume_ratio, time_str) -> Tuple[str, float, float]:
    parts = time_str.split(':')
    hour, minute = int(parts[0]), int(parts[1])
    time_of_day = dt_time(hour, minute)

    if price_position >= 0.98 and price_change_pct >= 1.0 and volume_ratio >= 5:
        return '拉高出货', -1.0, 0.85
    if price_position <= 0.3 and price_change_pct >= 0.3 and volume_ratio >= 2:
        return '真正拉升', 1.0, 0.80
    if price_position <= 0.3 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return '打压吸筹', 1.0, 0.80
    if price_position >= 0.9 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return '恐慌抛售', -1.0, 0.75
    if dt_time(9, 30) <= time_of_day <= dt_time(10, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return '疑似拉升', 1.0, 0.60
    if dt_time(14, 30) <= time_of_day <= dt_time(15, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return '疑似出货', -1.0, 0.60
    if price_change_pct >= 0.5:
        return '不确定', 0.3, 0.30
    elif price_change_pct <= -0.5:
        return '不确定', -0.3, 0.30
    else:
        return '不确定', 0.0, 0.0


def main():
    engine = create_engine(DB_URL)

    # ======== 1. 先确认字段存在 ========
    with engine.connect() as conn:
        cols = [r[0] for r in conn.execute(text(f"DESCRIBE {TABLE_NAME}")).fetchall()]
        for c in ['main_net_amount', 'main_behavior', 'main_confidence']:
            if c not in cols:
                print(f"[WARN] 字段 {c} 不存在，尝试添加...")
                conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {c} DECIMAL(15,2) DEFAULT 0" if c != 'main_behavior' else f"ALTER TABLE {TABLE_NAME} ADD COLUMN {c} VARCHAR(20) DEFAULT ''"))
                conn.commit()

    # ======== 2. 读取 000539 原始数据 ========
    with engine.connect() as conn:
        df = pd.read_sql(f"""
            SELECT stock_code, short_name, price, volume, amount, change_pct, time
            FROM {TABLE_NAME}
            WHERE stock_code = '{TEST_CODE}'
            ORDER BY time
        """, conn)

    if df.empty:
        print(f"[ERROR] {TEST_CODE} 无数据")
        return

    stock_name = df['short_name'].iloc[0]
    print(f"=== 测试股票: {TEST_CODE} {stock_name} ===")
    print(f"总记录数: {len(df)}")
    print()

    # ======== 3. 计算 ========
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')

    df = df.sort_values('time').reset_index(drop=True)

    # 周期变化
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)
    df['delta_change_pct'] = df['change_pct'].diff().fillna(0)

    # 当日高低
    day_high = df['price'].max()
    day_low = df['price'].min()
    price_range = day_high - day_low if day_high > day_low else 1.0

    df['price_position'] = ((df['price'] - day_low) / price_range).clip(0, 1)

    # 量能比
    median_vol = df['delta_volume'].median()
    if median_vol <= 0:
        median_vol = 20000
    df['volume_ratio'] = df['delta_volume'] / median_vol

    # 初始化
    df['main_net_amount'] = 0.0
    df['main_behavior'] = ''
    df['main_confidence'] = 0.0

    hit_count = 0
    for idx, row in df.iterrows():
        if row['delta_amount'] < MAIN_FORCE_CONFIG['min_amount'] or \
           row['delta_volume'] < MAIN_FORCE_CONFIG['min_volume']:
            continue

        behavior, direction, confidence = classify_behavior(
            row['price_position'], row['delta_change_pct'],
            row['volume_ratio'], row['time']
        )

        participation = calculate_participation_ratio(row['delta_amount'])

        if direction != 0:
            main_net = row['delta_amount'] * participation * direction * confidence
        else:
            main_net = 0.0

        df.at[idx, 'main_net_amount'] = round(main_net, 2)
        df.at[idx, 'main_behavior'] = behavior
        df.at[idx, 'main_confidence'] = round(confidence, 2)
        hit_count += 1

    # ======== 4. 输出详细结果（先不写库） ========
    print(f"当日价格: 高={day_high:.2f}, 低={day_low:.2f}, 振幅={price_range:.2f}")
    print(f"成交额中位数（每周期）: {df['delta_amount'].median():,.0f}")
    print(f"成交量中位数（每周期）: {median_vol:,.0f}")
    print()

    # 门槛统计
    above_amount = (df['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']).sum()
    above_volume = (df['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume']).sum()
    above_both = ((df['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']) &
                  (df['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume'])).sum()
    print(f"周期成交额 >= 30万: {above_amount} 条 ({above_amount/len(df)*100:.1f}%)")
    print(f"周期成交量 >= 200手: {above_volume} 条 ({above_volume/len(df)*100:.1f}%)")
    print(f"同时满足两个门槛: {above_both} 条 ({above_both/len(df)*100:.1f}%)")
    print(f"命中主力判断逻辑: {hit_count} 条 ({hit_count/len(df)*100:.1f}%)")
    print()

    # 有主力净额的记录
    df_main = df[df['main_net_amount'] != 0]
    if not df_main.empty:
        print(f"=== 有主力净额的记录: {len(df_main)} 条 ===")
        print()

        # 按行为类型统计
        behavior_stats = df_main.groupby('main_behavior').agg(
            count=('main_net_amount', 'count'),
            total=('main_net_amount', 'sum'),
            avg=('main_net_amount', 'mean'),
            avg_conf=('main_confidence', 'mean')
        ).reset_index()
        print("行为分布:")
        for _, row in behavior_stats.iterrows():
            print(f"  {row['main_behavior']}: {row['count']}次, "
                  f"总净额={row['total']:,.0f}, 平均={row['avg']:,.0f}, "
                  f"平均置信度={row['avg_conf']:.2f}")
        print()

        # 详细列出所有有主力净额的记录
        print("详细记录:")
        print(f"{'时间':<12} {'价格':>8} {'涨跌幅':>8} {'周期额':>14} {'周期量':>10} "
              f"{'价格位置':>8} {'量比':>6} {'主力净额':>14} {'行为':<10} {'置信度':>6}")
        print("-" * 120)
        for _, row in df_main.iterrows():
            print(f"{row['time']:<12} {row['price']:>8.2f} {row['change_pct']:>7.2f}% "
                  f"{row['delta_amount']:>13,.0f} {row['delta_volume']:>9,.0f} "
                  f"{row['price_position']:>7.2f} {row['volume_ratio']:>6.1f} "
                  f"{row['main_net_amount']:>13,.0f} {row['main_behavior']:<10} {row['main_confidence']:>5.2f}")

        print()
        total_net = df_main['main_net_amount'].sum()
        print(f"主力净额合计: {total_net:,.2f} 元")
        print(f"主力净流入: {df_main[df_main['main_net_amount'] > 0]['main_net_amount'].sum():,.2f} 元")
        print(f"主力净流出: {df_main[df_main['main_net_amount'] < 0]['main_net_amount'].sum():,.2f} 元")
    else:
        print("[INFO] 000539 今天没有触发主力判断逻辑的记录")
        print()
        # 输出最大的几个周期成交额，方便分析
        top_amount = df.nlargest(10, 'delta_amount')
        print("成交额最大的10个周期:")
        print(f"{'时间':<12} {'价格':>8} {'涨跌幅':>8} {'周期额':>14} {'周期量':>10} {'价格位置':>8}")
        print("-" * 80)
        for _, row in top_amount.iterrows():
            print(f"{row['time']:<12} {row['price']:>8.2f} {row['change_pct']:>7.2f}% "
                  f"{row['delta_amount']:>13,.0f} {row['delta_volume']:>9,.0f} "
                  f"{row['price_position']:>7.2f}")

    # ======== 5. 写入数据库 ========
    print()
    print("=== 写入数据库 ===")
    with engine.connect() as conn:
        # 先清除旧数据
        conn.execute(text(f"""
            UPDATE {TABLE_NAME}
            SET main_net_amount = 0, main_behavior = '', main_confidence = 0
            WHERE stock_code = '{TEST_CODE}'
        """))
        conn.commit()

        # 写入计算结果
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
        print(f"[OK] 已更新 {updated} 条记录到数据库")

    # ======== 6. 验证写入 ========
    print()
    print("=== 数据库验证 ===")
    with engine.connect() as conn:
        verify = pd.read_sql(f"""
            SELECT time, price, change_pct, main_net_amount, main_behavior, main_confidence
            FROM {TABLE_NAME}
            WHERE stock_code = '{TEST_CODE}'
            AND main_net_amount != 0
            ORDER BY time
        """, conn)

    if not verify.empty:
        print(f"数据库中 {TEST_CODE} 有 {len(verify)} 条主力净额记录:")
        for _, row in verify.iterrows():
            print(f"  {row['time']}: price={row['price']:.2f}, "
                  f"main_net={row['main_net_amount']:,.2f}, "
                  f"behavior={row['main_behavior']}, "
                  f"confidence={row['main_confidence']:.2f}")
    else:
        print(f"数据库中 {TEST_CODE} 无主力净额记录（所有记录不满足门槛条件）")

    print()
    print("[DONE] 测试完成")


if __name__ == "__main__":
    main()
