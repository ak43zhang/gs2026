#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债 - 数据回填脚本
直接调用 run_bond_backtest() 确保与量化回测100%一致的条件评估和P&L计算。

用法:
    # 方式1: 代码配置模式（修改 DEFAULT_CONFIG 后运行）
    python test/backfill_today.py

    # 方式2: 命令行参数模式
    python test/backfill_today.py --date 20260713
    python test/backfill_today.py --date 20260710 --date 20260711
"""

import sys
import argparse
from datetime import datetime

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import time as _time
import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard2.services.backtest_bond import run_bond_backtest
from gs2026.dashboard2.services.quant_screen_core import normalize_conditions


# ========== 默认配置（代码修改模式） ==========
# 当 USE_DEFAULT_CONFIG = True 时，使用以下配置，忽略命令行参数
USE_DEFAULT_CONFIG = True

DEFAULT_CONFIG = {
    'dates': ['20260713'],         # 回填日期列表
    'progress_interval': 1,        # 每N个方案输出一次进度（方案级别）
    'db_url': 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8',
}
# ========== 配置结束 ==========


engine = None


def get_engine(db_url):
    global engine
    if engine is None:
        engine = create_engine(db_url)
    return engine


def load_schemes(db_url):
    """
    从MySQL加载在用方案（与量化回测、量化选债完全一致）
    """
    eng = get_engine(db_url)
    with eng.connect() as conn:
        result = conn.execute(text("""
            SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct,
                   max_hold_time, price_offset, offset_mode, time_start, time_end
            FROM quant_screen_schemes
            WHERE is_active = 1
        """))
        schemes = []
        for row in result:
            schemes.append({
                'name': row.scheme_name,
                'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
                'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                'max_hold_time': int(row.max_hold_time) if row.max_hold_time else 30,
                'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                'offset_mode': row.offset_mode or 'fixed',
                'time_start': row.time_start or '09:30',
                'time_end': row.time_end or '15:00',
            })
        return schemes


def save_trades_to_db(trade_date, scheme_name, summary, trades, db_url):
    """
    将回测交易结果保存到 quant_screen_hits 表
    字段与回测结果完全对应
    """
    if not trades:
        return
    
    eng = get_engine(db_url)
    sql = text("""
        INSERT INTO quant_screen_hits 
        (trade_date, tick_time, scheme_name, bond_code, bond_name, 
         entry_price, entry_change_pct, signal_status,
         exit_time, exit_price, profit_pct, exit_reason, hold_seconds, max_price, min_price)
        VALUES 
        (:trade_date, :tick_time, :scheme_name, :bond_code, :bond_name,
         :entry_price, :entry_change_pct, :signal_status,
         :exit_time, :exit_price, :profit_pct, :exit_reason, :hold_seconds, :max_price, :min_price)
    """)
    
    with eng.connect() as conn:
        for trade in trades:
            conn.execute(sql, {
                'trade_date': trade_date,
                'tick_time': trade['signal_time'].replace(':', ''),
                'scheme_name': scheme_name,
                'bond_code': trade['bond_code'],
                'bond_name': trade.get('bond_name', ''),
                'entry_price': trade['entry_price'],
                'entry_change_pct': trade.get('profit_pct', 0),  # 入场时涨幅
                'signal_status': trade['exit_type'],  # tp/sl/timeout
                'exit_time': trade['exit_time'].replace(':', '') if trade.get('exit_time') else None,
                'exit_price': trade.get('exit_price'),
                'profit_pct': trade.get('profit_pct'),
                'exit_reason': trade['exit_type'],
                'hold_seconds': trade.get('duration_sec'),
                'max_price': trade.get('max_price'),
                'min_price': trade.get('min_price'),
            })
        conn.commit()


def run_backfill_single_date(trade_date: str, schemes: list, config: dict):
    """
    回填单日数据 — 逐方案调用 run_bond_backtest（与前端回测100%一致）
    """
    start_time = _time.time()
    table = f"monitor_zq_sssj_{trade_date}"
    db_url = config['db_url']
    eng = get_engine(db_url)

    print(f"\n{'='*60}")
    print(f"回填日期: {trade_date}")
    print(f"方案数量: {len(schemes)}")
    print(f"{'='*60}")

    # 1. 检查表是否存在
    with eng.connect() as conn:
        result = conn.execute(text(f"SHOW TABLES LIKE '{table}'"))
        if not result.fetchone():
            print(f"  ✗ 表 {table} 不存在，跳过")
            return

    # 2. 覆盖模式：清除该日期已有数据
    with eng.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM quant_screen_hits WHERE trade_date = :date
        """), {'date': trade_date})
        conn.commit()
        if result.rowcount:
            print(f"  清除旧记录: {result.rowcount} 条")

    # 3. 逐方案调用回测（与前端回测完全相同的函数）
    total_signals = 0
    total_tp = 0
    total_sl = 0

    for i, scheme in enumerate(schemes):
        scheme_start = _time.time()
        
        # 标准化条件格式
        conditions_config = normalize_conditions(scheme['conditions'])
        
        # 直接调用回测函数（100%一致的条件评估 + P&L计算）
        try:
            summary, trades = run_bond_backtest(
                engine=eng,
                date=trade_date,
                conditions=conditions_config['conditions'],
                groups=conditions_config['groups'],
                time_start=scheme['time_start'],
                time_end=scheme['time_end'],
                stop_loss_pct=scheme['stop_loss'],
                take_profit_pct=scheme['take_profit'],
                window_minutes=scheme['max_hold_time'],
                price_offset=scheme['price_offset'],
                offset_mode=scheme['offset_mode'],
            )
        except Exception as e:
            print(f"  ✗ 方案[{scheme['name']}] 回测失败: {e}")
            continue

        # 保存完整交易结果到DB
        save_trades_to_db(trade_date, scheme['name'], summary, trades, db_url)
        
        total_signals += summary.get('total_signals', 0)
        total_tp += summary.get('tp_count', 0)
        total_sl += summary.get('sl_count', 0)
        
        elapsed = _time.time() - scheme_start
        print(f"  [{i+1}/{len(schemes)}] 方案[{scheme['name']}]: "
              f"信号{summary.get('total_signals', 0)} "
              f"止盈{summary.get('tp_count', 0)} "
              f"止损{summary.get('sl_count', 0)} "
              f"胜率{summary.get('win_rate', 0):.1f}% "
              f"耗时{elapsed:.1f}s")

    elapsed = _time.time() - start_time
    print(f"\n  汇总: 信号{total_signals} 止盈{total_tp} 止损{total_sl} 总耗时{elapsed:.1f}s")


def main():
    # ====== 解析配置 ======
    if USE_DEFAULT_CONFIG:
        config = DEFAULT_CONFIG.copy()
    else:
        parser = argparse.ArgumentParser(description='量化选债回填脚本')
        parser.add_argument('--date', action='append', help='回填日期(YYYYMMDD)，默认今日')
        parser.add_argument('--db-url', default=DEFAULT_CONFIG['db_url'], help='数据库连接URL')
        args = parser.parse_args()
        
        config = {
            'dates': args.date if args.date else [datetime.now().strftime('%Y%m%d')],
            'db_url': args.db_url,
        }

    dates = config.get('dates', [datetime.now().strftime('%Y%m%d')])

    print(f"\n{'='*60}")
    print(f"量化选债回填（直接调用回测函数，结果100%一致）")
    print(f"日期: {', '.join(dates)}")
    print(f"{'='*60}")

    # 1. 加载方案
    print("\n加载方案...")
    schemes = load_schemes(config['db_url'])
    if not schemes:
        print("  ✗ 没有活跃方案，退出")
        return
    
    for s in schemes:
        raw_cond = s['conditions']
        config_norm = normalize_conditions(raw_cond)
        cond_count = len(config_norm['conditions'])
        group_count = len(config_norm['groups'])
        print(f"  - {s['name']} (条件:{cond_count} 组:{group_count} "
              f"时间:{s['time_start']}~{s['time_end']} "
              f"止盈:{s['take_profit']}% 止损:{s['stop_loss']}% "
              f"窗口:{s['max_hold_time']}min)")

    # 2. 逐日期回填
    for date in dates:
        run_backfill_single_date(date, schemes, config)

    print(f"\n{'='*60}")
    print(f"✓ 全部回填完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
