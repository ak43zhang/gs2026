#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化选债历史数据回填 - 7月9日
工作版本，分批读取避免内存问题
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import pandas as pd
from sqlalchemy import create_engine, text

TRADE_DATE = '20260709'
TIME_START = '093000'
TIME_END = '150000'

print(f"\n{'='*60}")
print(f"开始回填: {TRADE_DATE}")
print(f"时段: {TIME_START} - {TIME_END}")
print(f"{'='*60}\n")

# 创建引擎
engine = create_engine("mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8")

# 1. 加载方案
print("[1/4] 加载方案...")
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
            'offset_mode': row.offset_mode or 'fixed'
        })

if not schemes:
    print("[错误] 没有在用方案")
    sys.exit(1)

print(f"      加载 {len(schemes)} 个方案")
for sch in schemes:
    print(f"        - {sch['name']}")

# 构建方案参数
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
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT DISTINCT time FROM monitor_zq_sssj_{TRADE_DATE}
        WHERE time BETWEEN :start AND :end
        ORDER BY time
    """), {'start': TIME_START, 'end': TIME_END})
    tick_times = [str(row[0]) for row in result]

print(f"      共 {len(tick_times)} 个tick时间点")

# 3. 处理每个tick
print("\n[3/4] 处理tick数据...")
total_matches = 0
batch_data = []

for i, tick_time in enumerate(tick_times):
    # 读取该tick的数据
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT * FROM monitor_zq_sssj_{TRADE_DATE}
            WHERE time = :tick_time
        """), conn, params={'tick_time': tick_time})
    
    if df.empty:
        continue
    
    # 应用条件筛选
    matches = []
    seen = {}
    
    for scheme in schemes:
        name = scheme.get('name', '')
        conditions = scheme.get('conditions', [])
        if not conditions:
            continue
        
        mask = pd.Series(True, index=df.index)
        for c in conditions:
            field = c.get('field', '')
            if field not in df.columns:
                continue
            op = c.get('op', '>')
            val = float(c.get('value', 0))
            
            if op == '>':      mask &= df[field] > val
            elif op == '>=':   mask &= df[field] >= val
            elif op == '<':    mask &= df[field] < val
            elif op == '<=':   mask &= df[field] <= val
            elif op == '=':    mask &= df[field] == val
            elif op == '!=':   mask &= df[field] != val
            elif op == 'between':
                val2 = float(c.get('value2', val))
                mask &= (df[field] >= val) & (df[field] <= val2)
        
        hit = df[mask]
        
        for _, row in hit.iterrows():
            code = row.get('bond_code', '')
            if code in seen:
                for m in matches:
                    if m['bond_code'] == code:
                        m['scheme_names'].append(name)
                        break
            else:
                seen[code] = True
                matches.append({
                    'scheme_names': [name],
                    'bond_code': code,
                    'bond_name': row.get('bond_name', ''),
                    'price': round(float(row.get('price', 0)), 3),
                    'change_pct': round(float(row.get('change_pct', 0)), 2),
                    'amount': int(row.get('amount', 0)),
                })
    
    # 按涨幅排序
    matches.sort(key=lambda x: -x['change_pct'])
    
    if matches:
        bond_hit_counts = {}
        
        for match in matches:
            bond_code = match.get('bond_code', '')
            scheme_names = match.get('scheme_names', [])
            scheme_name = scheme_names[0] if scheme_names else ''
            params = scheme_params.get(scheme_name, {})
            
            signal_price = match.get('price', 0)
            price_offset = params.get('price_offset', 0)
            offset_mode = params.get('offset_mode', 'fixed')
            
            # 计算入场价
            if offset_mode == 'fixed':
                entry_price = signal_price + price_offset
            elif offset_mode == 'percent':
                entry_price = signal_price * (1 + price_offset / 100)
            else:
                entry_price = signal_price
            
            stop_loss_pct = params.get('stop_loss_pct', 0)
            take_profit_pct = params.get('take_profit_pct', 0)
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
            take_profit_price = entry_price * (1 + take_profit_pct / 100) if take_profit_pct else None
            
            bond_hit_counts[bond_code] = bond_hit_counts.get(bond_code, 0) + 1
            hit_seq = bond_hit_counts[bond_code]
            
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
    
    # 每100个tick批量插入
    if (i + 1) % 100 == 0:
        if batch_data:
            with engine.connect() as conn:
                for data in batch_data:
                    conn.execute(text("""
                        INSERT INTO quant_screen_hits 
                        (trade_date, tick_time, scheme_name, bond_code, bond_name, entry_price, entry_change_pct, 
                         entry_amount, stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price, 
                         max_hold_time, signal_status, hit_seq_today)
                        VALUES 
                        (:trade_date, :tick_time, :scheme_name, :bond_code, :bond_name, :entry_price, :entry_change_pct,
                         :entry_amount, :stop_loss_pct, :take_profit_pct, :stop_loss_price, :take_profit_price,
                         :max_hold_time, :signal_status, :hit_seq_today)
                    """), data)
                conn.commit()
            batch_data = []
        print(f"      进度: {i+1}/{len(tick_times)} ticks, 命中: {total_matches} 条")

# 插入剩余数据
if batch_data:
    with engine.connect() as conn:
        for data in batch_data:
            conn.execute(text("""
                INSERT INTO quant_screen_hits 
                (trade_date, tick_time, scheme_name, bond_code, bond_name, entry_price, entry_change_pct, 
                 entry_amount, stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price, 
                 max_hold_time, signal_status, hit_seq_today)
                VALUES 
                (:trade_date, :tick_time, :scheme_name, :bond_code, :bond_name, :entry_price, :entry_change_pct,
                 :entry_amount, :stop_loss_pct, :take_profit_pct, :stop_loss_price, :take_profit_price,
                 :max_hold_time, :signal_status, :hit_seq_today)
            """), data)
        conn.commit()

# 4. 汇总
print("\n[4/4] 回填完成!")
print(f"      处理ticks: {len(tick_times)}")
print(f"      总命中数: {total_matches}")
print("\n✓ 回填成功!")
