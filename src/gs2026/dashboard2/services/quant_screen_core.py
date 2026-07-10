"""
量化选债核心引擎
支持实时模式和回放模式
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from sqlalchemy import text


def apply_scheme_conditions(df: pd.DataFrame, schemes: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    统一的条件筛选逻辑
    
    Args:
        df: tick数据DataFrame
        schemes: 方案列表
        
    Returns:
        (matches, stats)
    """
    matches = []
    stats = {}
    seen = {}
    
    for scheme in schemes:
        name = scheme.get('name', '')
        conditions = scheme.get('conditions', [])
        
        if not conditions:
            stats[name] = 0
            continue
            
        # 应用条件
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
        stats[name] = len(hit)
        
        # 构建匹配结果
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
                    'amount_rank': int(row.get('amount_rank', 0)) if pd.notna(row.get('amount_rank')) else 0,
                    'slope_short': round(float(row.get('slope_short', 0)), 6) if pd.notna(row.get('slope_short')) else 0,
                    'min1_change_pct': round(float(row.get('min1_change_pct', 0)), 4) if pd.notna(row.get('min1_change_pct')) else 0,
                })
    
    # 按涨幅降序
    matches.sort(key=lambda x: -x['change_pct'])
    return matches, stats


def calculate_entry_price(signal_price: float, price_offset: float, offset_mode: str) -> float:
    """计算实际入场价（统一逻辑）"""
    if offset_mode == 'fixed':
        return signal_price + price_offset
    elif offset_mode == 'percent':
        return signal_price * (1 + price_offset / 100)
    return signal_price


def get_bond_hit_sequence(bond_code: str, trade_date: str, tick_time: str, engine) -> int:
    """
    获取债券当天的命中序号
    
    Args:
        bond_code: 债券代码
        trade_date: 交易日期
        tick_time: 当前tick时间
        engine: 数据库引擎
        
    Returns:
        命中序号（1开始）
    """
    from sqlalchemy import text
    
    sql = text("""
        SELECT COUNT(*) as cnt 
        FROM quant_screen_hits 
        WHERE trade_date = :trade_date 
          AND bond_code = :bond_code
          AND tick_time < :tick_time
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {
                'trade_date': trade_date,
                'bond_code': bond_code,
                'tick_time': tick_time
            }).fetchone()
            return (result[0] if result else 0) + 1
    except Exception as e:
        print(f"[get_bond_hit_sequence] Error: {e}")
        return 1


def save_quant_screen_hits(trade_date: str, tick_time: str, matches: List[Dict], 
                           schemes: List[Dict], df: pd.DataFrame, engine):
    """
    统一的保存命中记录逻辑
    
    Args:
        trade_date: 交易日期
        tick_time: tick时间
        matches: 匹配结果
        schemes: 方案列表
        df: 原始数据（用于查找额外字段）
        engine: 数据库引擎
    """
    from sqlalchemy import text
    
    if not matches:
        return
    
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
    
    # 准备插入数据
    insert_data = []
    for match in matches:
        bond_code = match.get('bond_code', '')
        scheme_names = match.get('scheme_names', [])
        scheme_name = scheme_names[0] if scheme_names else ''
        params = scheme_params.get(scheme_name, {})
        
        signal_price = match.get('price', 0)
        price_offset = params.get('price_offset', 0)
        offset_mode = params.get('offset_mode', 'fixed')
        
        # 计算实际入场价
        entry_price = calculate_entry_price(signal_price, price_offset, offset_mode)
        
        # 计算止损止盈价（基于入场价）
        stop_loss_pct = params.get('stop_loss_pct', 0)
        take_profit_pct = params.get('take_profit_pct', 0)
        stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
        take_profit_price = entry_price * (1 + take_profit_pct / 100) if take_profit_pct else None
        
        # 查找原始行获取额外字段
        row = df[df['bond_code'] == bond_code].iloc[0] if bond_code in df['bond_code'].values else None
        
        insert_data.append({
            'trade_date': trade_date,
            'tick_time': tick_time.replace(':', '') if ':' in str(tick_time) else tick_time,  # 格式化为HHMMSS
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
            'hit_seq_today': 1,  # 固定为1，展示时动态计算
        })
    
    # 批量插入（字段名匹配实际表结构）
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
        for data in insert_data:
            conn.execute(sql, data)
        conn.commit()
