#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回填 - 7月9日
批量版本，使用事务和批量插入
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import text
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.services.quant_screen_core import (
    apply_scheme_conditions,
    calculate_entry_price,
    get_bond_hit_sequence
)

TRADE_DATE = '20260709'
TIME_START = '093000'
TIME_END = '150000'


def main():
    print(f"\n{'='*60}")
    print(f"开始回填: {TRADE_DATE}")
    print(f"时段: {TIME_START} - {TIME_END}")
    print(f"{'='*60}\n")
    
    data_service = DataService()
    engine = data_service.engine
    
    # 1. 加载方案
    print("[1/4] 加载方案...")
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
    
    if not schemes:
        print("[错误] 没有在用方案")
        return
    print(f"      加载 {len(schemes)} 个方案")
    for sch in schemes:
        print(f"        - {sch['name']}")
    
    # 构建方案参数字典
    scheme_params = {}
    for scheme in schemes:
        name = scheme.get('name', '')
        scheme_params[name] = {
            'stop_loss_pct': scheme.get('stop_loss', 0),
            'take_profit_pct': scheme.get('take_profit', 0),
            'max_hold_time': scheme.get('max_hold_time'),
            'price_offset': scheme.get('price_offset', 0),
            'offset_mode': scheme.get('offset_mode', 'fixed'),
        }
    
    # 2. 获取tick时间点
    print("\n[2/4] 获取tick时间点...")
    sql = text(f"""
        SELECT DISTINCT time FROM monitor_zq_sssj_{TRADE_DATE}
        WHERE time BETWEEN :start AND :end
        ORDER BY time
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {'start': TIME_START, 'end': TIME_END})
        tick_times = [str(row[0]) for row in result]
    
    print(f"      共 {len(tick_times)} 个tick时间点")
    
    # 3. 处理tick数据
    print("\n[3/4] 处理tick数据...")
    total_matches = 0
    batch_data = []
    
    for i, tick_time in enumerate(tick_times):
        # 获取该tick的数据
        sql = text(f"""
            SELECT * FROM monitor_zq_sssj_{TRADE_DATE}
            WHERE time = :tick_time
        """)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'tick_time': tick_time})
        
        if df.empty:
            continue
        
        # 使用统一筛选引擎
        matches, stats = apply_scheme_conditions(df, schemes)
        
        if matches:
            # 准备批量插入数据
            for match in matches:
                bond_code = match.get('bond_code', '')
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
                
                hit_seq = get_bond_hit_sequence(bond_code, TRADE_DATE, tick_time.replace(':', ''), engine)
                
                batch_data.append({
                    'trade_date': TRADE_DATE,
                    'tick_time': tick_time.replace(':', ''),
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
            
            total_matches += len(matches)
        
        # 每100个tick批量插入一次
        if (i + 1) % 100 == 0:
            if batch_data:
                _batch_insert(engine, batch_data)
                batch_data = []
            print(f"      进度: {i+1}/{len(tick_times)} ticks, 累计命中: {total_matches} 条")
    
    # 插入剩余数据
    if batch_data:
        _batch_insert(engine, batch_data)
    
    # 4. 汇总
    print("\n[4/4] 回填完成!")
    print(f"      处理ticks: {len(tick_times)}")
    print(f"      总命中数: {total_matches}")
    print("\n✓ 回填成功!")


def _batch_insert(engine, batch_data):
    """批量插入"""
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


if __name__ == '__main__':
    main()
