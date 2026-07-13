#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债 - 数据回填脚本
与量化回测、量化选债(实时)使用完全相同的条件评估引擎和方案加载方式。

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
from gs2026.dashboard2.services.quant_screen_core import (
    apply_scheme_conditions,
    calculate_entry_price,
    expand_ext_indicators,
)


# ========== 默认配置（代码修改模式） ==========
# 当 USE_DEFAULT_CONFIG = True 时，使用以下配置，忽略命令行参数
USE_DEFAULT_CONFIG = True

DEFAULT_CONFIG = {
    'dates': ['20260713'],         # 回填日期列表，如 ['20260710', '20260711']
    'dedup_per_minute': True,      # 去重：同一分钟内每只债券只记录首次命中
    'progress_interval': 100,      # 每N个tick输出一次进度
    'db_url': 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8',
}
# ========== 配置结束 ==========

engine = None  # 延迟初始化


def get_engine(db_url):
    global engine
    if engine is None:
        engine = create_engine(db_url)
    return engine


def load_schemes(db_url):
    """
    从MySQL加载在用方案（与量化回测、量化选债完全一致）
    加载条件: is_active=1
    包含: conditions_json, time_start, time_end 等完整参数
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
                'max_hold_time': row.max_hold_time,
                'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                'offset_mode': row.offset_mode or 'fixed',
                'time_start': row.time_start or '09:30',
                'time_end': row.time_end or '15:00',
            })
        return schemes


def save_hits_batch(batch_data, db_url):
    """批量写入命中记录"""
    if not batch_data:
        return
    sql = text("""
        INSERT INTO quant_screen_hits 
        (trade_date, tick_time, scheme_name, bond_code, bond_name, entry_price, entry_change_pct, 
         entry_amount, stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price, 
         max_hold_time, signal_status, hit_seq_today)
        VALUES 
        (:trade_date, :tick_time, :scheme_name, :bond_code, :bond_name, :entry_price, :entry_change_pct,
         :entry_amount, :stop_loss_pct, :take_profit_pct, :stop_loss_price, :take_profit_price,
         :max_hold_time, :signal_status, :hit_seq_today)
    """)
    eng = get_engine(db_url)
    with eng.connect() as conn:
        for data in batch_data:
            conn.execute(sql, data)
        conn.commit()


def run_backfill_single_date(trade_date: str, schemes: list, config: dict):
    """
    回填单日数据
    
    Args:
        trade_date: 日期字符串 YYYYMMDD
        schemes: 方案列表（从MySQL加载）
        config: 配置字典
    """
    start_time = _time.time()
    table = f"monitor_zq_sssj_{trade_date}"
    db_url = config['db_url']
    eng = get_engine(db_url)

    # 从方案中获取时间范围（取所有方案的最大范围）
    time_start = min(s['time_start'] for s in schemes)
    time_end = max(s['time_end'] for s in schemes)
    
    # 标准化时间格式（支持 HH:MM 和 HHMMSS）
    if ':' in time_start:
        time_start_sql = time_start + ':00' if len(time_start) == 5 else time_start
    else:
        time_start_sql = time_start
    if ':' in time_end:
        time_end_sql = time_end + ':00' if len(time_end) == 5 else time_end
    else:
        time_end_sql = time_end

    print(f"\n{'='*60}")
    print(f"回填日期: {trade_date}")
    print(f"时间范围: {time_start_sql} ~ {time_end_sql}")
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

    # 3. 获取tick时间点
    with eng.connect() as conn:
        result = conn.execute(text(f"""
            SELECT DISTINCT time FROM `{table}`
            WHERE time >= :start AND time <= :end
            ORDER BY time
        """), {'start': time_start_sql, 'end': time_end_sql})
        tick_times = [str(row[0]) for row in result]
    
    if not tick_times:
        print(f"  ✗ 无数据，跳过")
        return
    print(f"  tick数量: {len(tick_times)}")

    # 4. 构建方案参数
    scheme_params = {}
    for scheme in schemes:
        scheme_params[scheme['name']] = {
            'stop_loss_pct': scheme.get('stop_loss', 0),
            'take_profit_pct': scheme.get('take_profit', 0),
            'max_hold_time': scheme.get('max_hold_time'),
            'price_offset': scheme.get('price_offset', 0),
            'offset_mode': scheme.get('offset_mode', 'fixed'),
        }

    # 5. 逐tick处理
    total_matches = 0
    total_saved = 0
    batch_data = []
    seen_this_minute = {}  # 去重: {bond_code_HHMM: True}

    for i, tick_time in enumerate(tick_times):
        # 读取该tick数据
        with eng.connect() as conn:
            df = pd.read_sql(text(f"""
                SELECT * FROM `{table}` WHERE time = :t
            """), conn, params={'t': tick_time})

        if df.empty:
            continue

        # 展开 ext_indicators JSON（统一函数）
        df = expand_ext_indicators(df)

        # 统一条件评估（与量化回测、量化选债完全相同）
        matches, stats = apply_scheme_conditions(df, schemes)
        total_matches += len(matches)

        if matches:
            tick_time_clean = tick_time.replace(':', '')
            current_minute = tick_time_clean[:4]  # HHMM

            for match in matches:
                bond_code = match.get('bond_code', '')

                # 去重：每分钟每债只记录首次
                if config['dedup_per_minute']:
                    dedup_key = f"{bond_code}_{current_minute}"
                    if dedup_key in seen_this_minute:
                        continue
                    seen_this_minute[dedup_key] = True

                # 计算入场价（与量化回测一致）
                scheme_names = match.get('scheme_names', [])
                scheme_name = scheme_names[0] if scheme_names else ''
                params = scheme_params.get(scheme_name, {})

                signal_price = match.get('price', 0)
                price_offset = params.get('price_offset', 0)
                offset_mode = params.get('offset_mode', 'fixed')
                entry_price = calculate_entry_price(signal_price, price_offset, offset_mode)

                stop_loss_pct = params.get('stop_loss_pct', 0)
                take_profit_pct = params.get('take_profit_pct', 0)
                stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
                take_profit_price = entry_price * (1 + take_profit_pct / 100) if take_profit_pct else None

                batch_data.append({
                    'trade_date': trade_date,
                    'tick_time': tick_time_clean,
                    'scheme_name': scheme_name,
                    'bond_code': bond_code,
                    'bond_name': match.get('bond_name', ''),
                    'entry_price': entry_price,
                    'entry_change_pct': match.get('change_pct', 0),
                    'entry_amount': match.get('amount', 0),
                    'stop_loss_pct': stop_loss_pct,
                    'take_profit_pct': take_profit_pct,
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'max_hold_time': params.get('max_hold_time'),
                    'signal_status': 'entry',
                    'hit_seq_today': 1,
                })
                total_saved += 1

        # 定期批量写入并输出进度
        if (i + 1) % config['progress_interval'] == 0:
            if batch_data:
                save_hits_batch(batch_data, db_url)
                batch_data = []
            elapsed = _time.time() - start_time
            print(f"  [{i+1}/{len(tick_times)}] "
                  f"命中:{total_matches} 保存:{total_saved} "
                  f"耗时:{elapsed:.1f}s")

    # 写入剩余数据
    if batch_data:
        save_hits_batch(batch_data, db_url)

    elapsed = _time.time() - start_time
    print(f"  完成: 命中{total_matches} 保存{total_saved}(去重后) 耗时{elapsed:.1f}s")


def main():
    # ====== 解析配置（代码配置模式 vs 命令行参数）======
    if USE_DEFAULT_CONFIG:
        config = DEFAULT_CONFIG.copy()
    else:
        parser = argparse.ArgumentParser(description='量化选债回填脚本')
        parser.add_argument('--date', action='append', help='回填日期(YYYYMMDD)，可多次指定，默认今日')
        parser.add_argument('--db-url', default=DEFAULT_CONFIG['db_url'], help='数据库连接URL')
        parser.add_argument('--progress', type=int, default=DEFAULT_CONFIG['progress_interval'], help='进度输出间隔')
        parser.add_argument('--no-dedup', action='store_true', help='关闭每分钟去重')
        args = parser.parse_args()
        
        config = {
            'dates': args.date if args.date else [datetime.now().strftime('%Y%m%d')],
            'dedup_per_minute': not args.no_dedup,
            'progress_interval': args.progress,
            'db_url': args.db_url,
        }

    # 日期默认今日
    dates = config.get('dates', [datetime.now().strftime('%Y%m%d')])

    print(f"\n{'='*60}")
    print(f"量化选债回填")
    print(f"日期: {', '.join(dates)}")
    print(f"去重: {'每分钟' if config['dedup_per_minute'] else '关闭'}")
    print(f"{'='*60}")

    # 1. 加载方案（从MySQL，与量化回测/选债完全一致）
    print("\n加载方案...")
    schemes = load_schemes(config['db_url'])
    if not schemes:
        print("  ✗ 没有活跃方案，退出")
        return
    
    for s in schemes:
        raw_cond = s['conditions']
        if isinstance(raw_cond, dict):
            cond_count = len(raw_cond.get('conditions', []))
        elif isinstance(raw_cond, list):
            cond_count = len(raw_cond)
        else:
            cond_count = 0
        print(f"  - {s['name']} (条件:{cond_count} "
              f"时间:{s['time_start']}~{s['time_end']} "
              f"止盈:{s['take_profit']}% 止损:{s['stop_loss']}%)")

    # 2. 逐日期回填
    for date in dates:
        run_backfill_single_date(date, schemes, config)

    print(f"\n{'='*60}")
    print(f"✓ 全部回填完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
