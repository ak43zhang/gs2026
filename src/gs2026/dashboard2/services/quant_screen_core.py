"""
量化选债核心引擎（统一条件评估）
量化回测、量化选债(实时)、量化回填 共用同一套条件评估逻辑
"""

import json as _json
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Union
from sqlalchemy import text


# ============================================================
# 统一条件评估引擎
# ============================================================

def normalize_conditions(raw) -> dict:
    """
    标准化条件格式（兼容所有历史版本）
    
    输入:
        - 旧版格式: [{field, op, value}, ...]
        - 新版格式: {"conditions": [...], "groups": [...]}
        - 空值: None, [], {}
        
    输出:
        {"conditions": [...], "groups": [...]}
    """
    if isinstance(raw, dict):
        return {
            'conditions': raw.get('conditions', []),
            'groups': raw.get('groups', []),
        }
    elif isinstance(raw, list):
        return {'conditions': raw, 'groups': []}
    return {'conditions': [], 'groups': []}


def expand_ext_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    展开 ext_indicators JSON列为独立列（供条件评估使用）
    如果已展开或列不存在则跳过
    
    展开后的列: weighted_slope_2m, change_1m_pct, price_acceleration,
               mkt_weighted_slope_2m, mkt_change_1m_pct, mkt_price_acceleration
    """
    if 'ext_indicators' not in df.columns:
        return df
    
    try:
        ext_parsed = df['ext_indicators'].apply(
            lambda x: _json.loads(x) if isinstance(x, str) and x else {}
        )
        ext_expanded = pd.json_normalize(ext_parsed)
        for col in ext_expanded.columns:
            if col not in df.columns:
                df[col] = ext_expanded[col].values
    except Exception:
        pass  # 解析失败不影响主流程
    
    return df


def evaluate_conditions(df: pd.DataFrame, conditions_config) -> pd.Series:
    """
    【统一核心】条件评估引擎
    
    量化回测、量化选债(实时)、量化回填 共用此函数。
    修改此函数的逻辑，三个系统同步生效。
    
    Args:
        df: 数据DataFrame（需已展开ext_indicators）
        conditions_config: dict或list（自动normalize）
        
    Returns:
        pd.Series(bool) — True表示该行满足所有条件
    """
    if df.empty:
        return pd.Series(dtype=bool)
    
    config = normalize_conditions(conditions_config)
    conditions = config['conditions']
    groups = config['groups']
    
    # 基础条件 (AND)
    mask = _eval_condition_list(df, conditions)
    
    # 条件组（组间AND，每组按mode处理）
    if groups:
        for group in groups:
            mode = group.get('mode', 'and')
            if mode == 'or' and group.get('subgroups'):
                # OR模式：子条件组间OR（每个子组内AND）
                group_mask = pd.Series(False, index=df.index)
                for subgroup in group['subgroups']:
                    sub_conds = subgroup.get('conditions', [])
                    if sub_conds:
                        group_mask |= _eval_condition_list(df, sub_conds)
                mask &= group_mask
            else:
                # AND模式：组内条件AND
                g_conds = group.get('conditions', [])
                if g_conds:
                    mask &= _eval_condition_list(df, g_conds)
    
    return mask


def _eval_condition_list(df: pd.DataFrame, conditions: list) -> pd.Series:
    """评估条件列表（AND逻辑）"""
    mask = pd.Series(True, index=df.index)
    for c in conditions:
        if not isinstance(c, dict):
            continue
        mask &= _eval_single_condition(df, c)
    return mask


def _eval_single_condition(df: pd.DataFrame, c: dict) -> pd.Series:
    """
    评估单个条件
    
    支持:
        - 普通比较: field > value
        - 字段间比较: field > compare_field (is_field_compare=True)
        - 区间: field BETWEEN value AND value2
    
    字段不存在时返回全True（跳过该条件）
    """
    field = c.get('field', '')
    if not field or field not in df.columns:
        return pd.Series(True, index=df.index)
    
    op = c.get('op', '>')
    is_field_compare = c.get('is_field_compare', False)
    
    # 左侧：转为数值
    lhs = pd.to_numeric(df[field], errors='coerce')
    
    # 右侧：字段间比较 或 固定值
    if is_field_compare and c.get('compare_field'):
        compare_field = c['compare_field']
        if compare_field not in df.columns:
            return pd.Series(True, index=df.index)
        rhs = pd.to_numeric(df[compare_field], errors='coerce')
    else:
        try:
            rhs = float(c.get('value', 0))
        except (ValueError, TypeError):
            rhs = 0.0
    
    # 执行比较
    if op == '>':       return lhs > rhs
    elif op == '>=':    return lhs >= rhs
    elif op == '<':     return lhs < rhs
    elif op == '<=':    return lhs <= rhs
    elif op == '=':     return lhs == rhs
    elif op == '!=':    return lhs != rhs
    elif op == 'between':
        try:
            val1 = float(c.get('value', 0))
            val2 = float(c.get('value2', val1))
        except (ValueError, TypeError):
            val1, val2 = 0.0, 0.0
        return (lhs >= val1) & (lhs <= val2)
    
    return pd.Series(True, index=df.index)


# ============================================================
# 多方案批量评估入口（实时选债 + 回填共用）
# ============================================================

def apply_scheme_conditions(df: pd.DataFrame, schemes: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    多方案批量评估
    
    内部调用 normalize_conditions + evaluate_conditions，
    确保与量化回测使用完全相同的评估逻辑。
    
    Args:
        df: tick数据DataFrame（需已展开ext_indicators）
        schemes: 方案列表，每个方案包含 name、conditions 等
        
    Returns:
        (matches, stats)
    """
    matches = []
    stats = {}
    seen = {}
    
    for scheme in schemes:
        name = scheme.get('name', '')
        raw_conditions = scheme.get('conditions', [])
        
        # 统一格式化
        config = normalize_conditions(raw_conditions)
        
        if not config['conditions'] and not config['groups']:
            stats[name] = 0
            continue
        
        # 统一评估（与回测完全相同的逻辑）
        mask = evaluate_conditions(df, config)
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
