#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回填 - 7月9日
同步版本，使用统一核心引擎
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


def check_table_exists(engine, table_name):
    """检查表是否存在"""
    check_sql = text("""
        SELECT COUNT(*) FROM information_schema.tables 
        WHERE table_schema = DATABASE() AND table_name = :table_name
    """)
    try:
        with engine.connect() as conn:
            result = conn.execute(check_sql, {'table_name': table_name}).scalar()
            return result > 0
    except Exception as e:
        print(f"[检查表失败] {table_name}: {e}")
        return False


def get_latest_trading_date(engine):
    """获取最新交易日"""
    try:
        sql = text("""
            SELECT trade_date FROM data_jyrl 
            WHERE trade_date <= CURDATE() AND trade_status = '1'
            ORDER BY trade_date DESC LIMIT 1
        """)
        with engine.connect() as conn:
            result = conn.execute(sql).fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"[获取最新交易日失败] {e}")
        return None


def fetch_tick_groups(engine, trade_date, time_start, time_end):
    """获取tick数据分组"""
    table_name = f"monitor_zq_sssj_{trade_date}"
    
    # 检查表是否存在
    if not check_table_exists(engine, table_name):
        latest_date = get_latest_trading_date(engine)
        if latest_date:
            print(f"[警告] 表 {table_name} 不存在，使用最新交易日: {latest_date}")
            table_name = f"monitor_zq_sssj_{latest_date}"
            trade_date = latest_date
        else:
            print(f"[错误] 表 {table_name} 不存在，且未找到可用交易日")
            return [], trade_date
    
    # 查询所有字段
    sql = text(f"""
        SELECT * FROM {table_name}
        WHERE time BETWEEN :start AND :end
        ORDER BY time
    """)
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'start': time_start, 'end': time_end})
    except Exception as e:
        print(f"[查询失败] {table_name}: {e}")
        return [], trade_date
    
    if df.empty:
        print(f"[警告] {table_name} 在 {time_start}-{time_end} 无数据")
        return [], trade_date
    
    # 按time分组
    groups = []
    for tick_time, group in df.groupby('time'):
        groups.append((str(tick_time), group))
    
    return groups, trade_date


def load_schemes_from_mysql(engine):
    """从MySQL加载在用方案"""
    try:
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
    except Exception as e:
        print(f"[加载方案失败] {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    print(f"\n{'='*60}")
    print(f"开始回填: {TRADE_DATE}")
    print(f"时段: {TIME_START} - {TIME_END}")
    print(f"{'='*60}\n")
    
    # 初始化
    data_service = DataService()
    engine = data_service.engine
    
    # 1. 加载方案
    print("[1/4] 加载方案...")
    schemes = load_schemes_from_mysql(engine)
    if not schemes:
        print("[错误] 没有在用方案")
        return
    print(f"      加载 {len(schemes)} 个方案:")
    for sch in schemes:
        print(f"        - {sch['name']}")
    
    # 2. 获取tick数据
    print("\n[2/4] 加载tick数据...")
    tick_groups, actual_date = fetch_tick_groups(engine, TRADE_DATE, TIME_START, TIME_END)
    if not tick_groups:
        print("[错误] 无tick数据")
        return
    print(f"      共 {len(tick_groups)} 个tick时间点")
    
    # 3. 遍历处理每个tick
    print("\n[3/4] 处理tick数据...")
    total_matches = 0
    
    for i, (tick_time, df) in enumerate(tick_groups):
        # 使用统一筛选引擎
        matches, stats = apply_scheme_conditions(df, schemes)
        
        if matches:
            # 使用统一保存逻辑
            save_quant_screen_hits(actual_date, tick_time, matches, schemes, df, engine)
            total_matches += len(matches)
        
        # 显示进度
        if (i + 1) % 100 == 0 or i == len(tick_groups) - 1:
            print(f"      进度: {i+1}/{len(tick_groups)} ticks, 累计命中: {total_matches} 条")
    
    # 4. 汇总
    print("\n[4/4] 回填完成!")
    print(f"      处理ticks: {len(tick_groups)}")
    print(f"      总命中数: {total_matches}")
    print("\n✓ 回填成功!")


if __name__ == '__main__':
    main()
