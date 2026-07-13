#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债 - 今日数据回填脚本
逻辑与实时场景完全一致（使用quant_screen_core统一引擎）
"""

import sys
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

# ===== 配置 =====
TRADE_DATE = '20260710'
TIME_START = '093000'
TIME_END = '150000'
DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
PROGRESS_INTERVAL = 50  # 每50个tick输出一次进度
# 去重：同一分钟内每只债券只记录首次命中
DEDUP_PER_MINUTE = True

engine = create_engine(DB_URL)


def delete_test_record():
    """删除测试数据"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM quant_screen_hits 
            WHERE trade_date = :date AND tick_time = '104248' 
              AND bond_code = '123195' AND scheme_name = '基础'
        """), {'date': TRADE_DATE})
        conn.commit()
        deleted = result.rowcount
        if deleted:
            print(f"  ✓ 删除测试记录: 123195 @ 10:42:48 ({deleted}条)")
        else:
            print(f"  - 测试记录不存在，无需删除")


def load_schemes():
    """从MySQL加载在用方案（与实时逻辑一致）"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct,
                   max_hold_time, price_offset, offset_mode
            FROM quant_screen_schemes
            WHERE is_active = 1 AND use_realtime = 1
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
            })
        return schemes


def save_hits_batch(batch_data):
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
    with engine.connect() as conn:
        for data in batch_data:
            conn.execute(sql, data)
        conn.commit()


def main():
    start_time = _time.time()
    
    print(f"\n{'='*60}")
    print(f"量化选债回填: {TRADE_DATE}")
    print(f"时段: {TIME_START} - {TIME_END}")
    print(f"去重: {'每分钟每债仅首次' if DEDUP_PER_MINUTE else '不去重'}")
    print(f"{'='*60}\n")

    # 0. 删除测试数据
    print("[0/5] 清理测试数据...")
    delete_test_record()

    # 1. 加载方案
    print("\n[1/5] 加载方案...")
    schemes = load_schemes()
    if not schemes:
        print("  ✗ 没有在用方案，退出")
        return
    print(f"  ✓ {len(schemes)} 个方案:")
    for s in schemes:
        print(f"    - {s['name']} (条件:{len(s['conditions'])} "
              f"止盈:{s['take_profit']}% 止损:{s['stop_loss']}% "
              f"偏移:{s['price_offset']}{s['offset_mode']})")

    # 构建方案参数
    scheme_params = {}
    for scheme in schemes:
        scheme_params[scheme['name']] = {
            'stop_loss_pct': scheme.get('stop_loss', 0),
            'take_profit_pct': scheme.get('take_profit', 0),
            'max_hold_time': scheme.get('max_hold_time'),
            'price_offset': scheme.get('price_offset', 0),
            'offset_mode': scheme.get('offset_mode', 'fixed'),
        }

    # 2. 获取tick时间点
    print("\n[2/5] 获取tick时间点...")
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT DISTINCT time FROM monitor_zq_sssj_{TRADE_DATE}
            WHERE time BETWEEN :start AND :end
            ORDER BY time
        """), {'start': TIME_START, 'end': TIME_END})
        tick_times = [str(row[0]) for row in result]
    print(f"  ✓ 共 {len(tick_times)} 个tick")

    # 3. 清除今日已有回填数据（避免重复）
    print("\n[3/5] 清除今日已有数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM quant_screen_hits WHERE trade_date = :date
        """), {'date': TRADE_DATE})
        conn.commit()
        print(f"  ✓ 清除 {result.rowcount} 条旧记录")

    # 4. 逐tick处理
    print(f"\n[4/5] 处理tick数据（每{PROGRESS_INTERVAL}个tick输出进度）...")
    total_matches = 0
    total_saved = 0
    batch_data = []
    # 去重字典: {bond_code: last_saved_minute}
    seen_this_minute = {}  # key=bond_code, value=minute_str

    for i, tick_time in enumerate(tick_times):
        # 读取该tick数据
        with engine.connect() as conn:
            df = pd.read_sql(text(f"""
                SELECT * FROM monitor_zq_sssj_{TRADE_DATE} WHERE time = :t
            """), conn, params={'t': tick_time})

        if df.empty:
            continue

        # 展开 ext_indicators JSON（统一函数）
        df = expand_ext_indicators(df)

        # 统一筛选引擎（与实时逻辑完全一致）
        matches, stats = apply_scheme_conditions(df, schemes)
        total_matches += len(matches)

        if matches:
            # 当前tick的分钟
            tick_time_clean = tick_time.replace(':', '')
            current_minute = tick_time_clean[:4]  # HHMM

            for match in matches:
                bond_code = match.get('bond_code', '')

                # 去重：每分钟每债只记录首次
                if DEDUP_PER_MINUTE:
                    dedup_key = f"{bond_code}_{current_minute}"
                    if dedup_key in seen_this_minute:
                        continue
                    seen_this_minute[dedup_key] = True

                # 计算入场价（与实时一致）
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

                # 命中序号：保存时固定为1，展示时动态计算
                hit_seq = 1

                batch_data.append({
                    'trade_date': TRADE_DATE,
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
                    'hit_seq_today': hit_seq,
                })
                total_saved += 1

        # 每50 tick批量写入并输出进度
        if (i + 1) % PROGRESS_INTERVAL == 0:
            if batch_data:
                save_hits_batch(batch_data)
                batch_data = []
            elapsed = _time.time() - start_time
            print(f"  [{i+1}/{len(tick_times)}] "
                  f"命中:{total_matches} 保存:{total_saved} "
                  f"耗时:{elapsed:.1f}s")

    # 写入剩余数据
    if batch_data:
        save_hits_batch(batch_data)

    # 5. 汇总
    elapsed = _time.time() - start_time
    print(f"\n[5/5] 回填完成!")
    print(f"  处理ticks: {len(tick_times)}")
    print(f"  总命中次数: {total_matches}")
    print(f"  实际保存: {total_saved} (去重后)")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"\n{'='*60}")
    print(f"✓ 回填成功!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
