#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回填 - 7月9日
快速版本，分批处理
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import text
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.services.quant_screen_core import (
    apply_scheme_conditions,
    save_quant_screen_hits
)

TRADE_DATE = '20260709'
TIME_START = '093000'
TIME_END = '150000'
BATCH_SIZE = 500  # 每批处理500个tick


def load_schemes(engine):
    """加载方案"""
    sql = text("""
        SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, 
               max_hold_time, price_offset, offset_mode
        FROM quant_screen_schemes 
        WHERE is_active = 1 AND use_realtime = 1
    """)
    with engine.connect() as conn:
        result = conn.execute(sql)
        schemes = []
        import json
        for row in result:
            schemes.append({
                'name': row.scheme_name,
                'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
                'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                'max_hold_time': row.max_hold_time,
                'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                'offset_mode': row.offset_mode or 'fixed'
            })
        return schemes


def get_tick_times(engine, trade_date, time_start, time_end):
    """获取所有tick时间点"""
    table_name = f"monitor_zq_sssj_{trade_date}"
    sql = text(f"""
        SELECT DISTINCT time FROM {table_name}
        WHERE time BETWEEN :start AND :end
        ORDER BY time
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'start': time_start, 'end': time_end})
        return [str(row[0]) for row in result]


def fetch_tick_data(engine, trade_date, tick_time):
    """获取单个tick的数据"""
    table_name = f"monitor_zq_sssj_{trade_date}"
    sql = text(f"""
        SELECT * FROM {table_name}
        WHERE time = :tick_time
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={'tick_time': tick_time})


def main():
    print(f"\n{'='*60}")
    print(f"开始回填: {TRADE_DATE}")
    print(f"时段: {TIME_START} - {TIME_END}")
    print(f"{'='*60}\n")
    
    data_service = DataService()
    engine = data_service.engine
    
    # 1. 加载方案
    print("[1/4] 加载方案...")
    schemes = load_schemes(engine)
    if not schemes:
        print("[错误] 没有在用方案")
        return
    print(f"      加载 {len(schemes)} 个方案")
    for sch in schemes:
        print(f"        - {sch['name']}")
    
    # 2. 获取tick时间点
    print("\n[2/4] 获取tick时间点...")
    tick_times = get_tick_times(engine, TRADE_DATE, TIME_START, TIME_END)
    print(f"      共 {len(tick_times)} 个tick时间点")
    
    # 3. 分批处理
    print("\n[3/4] 处理tick数据...")
    total_matches = 0
    
    for i, tick_time in enumerate(tick_times):
        # 获取该tick的数据
        df = fetch_tick_data(engine, TRADE_DATE, tick_time)
        if df.empty:
            continue
        
        # 使用统一筛选引擎
        matches, stats = apply_scheme_conditions(df, schemes)
        
        if matches:
            # 使用统一保存逻辑
            save_quant_screen_hits(TRADE_DATE, tick_time, matches, schemes, df, engine)
            total_matches += len(matches)
        
        # 显示进度
        if (i + 1) % 100 == 0 or i == len(tick_times) - 1:
            print(f"      进度: {i+1}/{len(tick_times)} ticks, 累计命中: {total_matches} 条")
    
    # 4. 汇总
    print("\n[4/4] 回填完成!")
    print(f"      处理ticks: {len(tick_times)}")
    print(f"      总命中数: {total_matches}")
    print("\n✓ 回填成功!")


if __name__ == '__main__':
    main()
