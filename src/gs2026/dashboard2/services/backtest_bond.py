"""
债券量化回测引擎

两阶段查询策略：
  阶段1：条件下推SQL → 获取信号点（几十~几百条）
  阶段2：按信号bond_code + 时间窗口 → 获取价格序列（几千~几万条）
  阶段3：逐信号逐tick判定止盈/止损/超时
"""

import pandas as pd
import numpy as np
from sqlalchemy import text


# ====== 工具函数 ======
def _td_to_str(td):
    """格式化 timedelta 为 HH:MM:SS（健壮版）"""
    try:
        # 如果已经是 timedelta 对象
        if hasattr(td, 'total_seconds'):
            total_sec = int(td.total_seconds())
        # 如果是字符串
        elif isinstance(td, str):
            # 尝试解析为 timedelta
            td = pd.Timedelta(td)
            total_sec = int(td.total_seconds())
        else:
            # 其他类型，尝试转换
            td = pd.Timedelta(str(td))
            total_sec = int(td.total_seconds())
        
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception as e:
        # 转换失败时返回原始值的字符串表示
        print(f"[WARN] _td_to_str failed for value: {td}, type: {type(td)}, error: {e}")
        return str(td)[:8]  # 截断到8字符避免过长


# ====== 字段配置（扩展点：新增字段只需追加此列表）======
BACKTEST_FIELDS = [
    {'name': 'price', 'label': '现价', 'group': '价格类', 'type': 'float'},
    {'name': 'open', 'label': '开盘价', 'group': '价格类', 'type': 'float'},
    {'name': 'high', 'label': '最高价', 'group': '价格类', 'type': 'float'},
    {'name': 'low', 'label': '最低价', 'group': '价格类', 'type': 'float'},
    {'name': 'pre_close', 'label': '昨收', 'group': '价格类', 'type': 'float'},
    {'name': 'change', 'label': '涨跌额', 'group': '涨跌类', 'type': 'float'},
    {'name': 'change_pct', 'label': '涨跌幅(%)', 'group': '涨跌类', 'type': 'float'},
    {'name': 'volume', 'label': '成交量', 'group': '成交类', 'type': 'float'},
    {'name': 'amount', 'label': '成交金额', 'group': '成交类', 'type': 'float'},
    {'name': 'min1_change_pct', 'label': '1分钟涨幅(%)', 'group': '1分钟类', 'type': 'float'},
    {'name': 'min1_amount', 'label': '1分钟金额', 'group': '1分钟类', 'type': 'float'},
    {'name': 'amount_rank', 'label': '金额排名', 'group': '成交类', 'type': 'int'},
    {'name': 'slope_short', 'label': '斜率(3min)', 'group': '趋势类', 'type': 'float'},
    {'name': 'slope_long', 'label': '斜率(15min)', 'group': '趋势类', 'type': 'float'},
    {'name': 'peak_vol_bias', 'label': '放量高点偏离(%)', 'group': '趋势类', 'type': 'float'},
    {'name': 'high_distance', 'label': '日内高点距离(%)', 'group': '趋势类', 'type': 'float'},
    {'name': 'mkt_slope_short', 'label': '大盘斜率(3min)', 'group': '大盘类', 'type': 'float'},
    {'name': 'mkt_slope_long', 'label': '大盘斜率(15min)', 'group': '大盘类', 'type': 'float'},
    {'name': 'mkt_peak_vol_bias', 'label': '大盘放量偏离(%)', 'group': '大盘类', 'type': 'float'},
    {'name': 'mkt_high_distance', 'label': '大盘高点距离(%)', 'group': '大盘类', 'type': 'float'},
    # 扩展指标（存储在 ext_indicators JSON 列中）
    {'name': 'weighted_slope_2m', 'label': '加权斜率(2min)', 'group': '趋势类(快)', 'type': 'float', 'json_field': True},
    {'name': 'change_1m_pct', 'label': '1分钟变化率(%)', 'group': '趋势类(快)', 'type': 'float', 'json_field': True},
    {'name': 'price_acceleration', 'label': '加速度', 'group': '趋势类(快)', 'type': 'float', 'json_field': True},
    {'name': 'mkt_weighted_slope_2m', 'label': '大盘加权斜率(2min)', 'group': '大盘类(快)', 'type': 'float', 'json_field': True},
    {'name': 'mkt_change_1m_pct', 'label': '大盘1分钟变化率(%)', 'group': '大盘类(快)', 'type': 'float', 'json_field': True},
    {'name': 'mkt_price_acceleration', 'label': '大盘加速度', 'group': '大盘类(快)', 'type': 'float', 'json_field': True},
    # 形态类
    {'name': 'is_body_up', 'label': '实体阳', 'group': '形态类', 'type': 'int'},
    {'name': 'is_body_down', 'label': '实体阴', 'group': '形态类', 'type': 'int'},
    {'name': 'is_body_flat', 'label': '实体平', 'group': '形态类', 'type': 'int'},
]

VALID_FIELDS = {f['name'] for f in BACKTEST_FIELDS}
VALID_OPS = {'>', '>=', '<', '<=', '=', '!=', 'between'}

# ext_indicators JSON字段集合（用于SQL构建时判断）
_JSON_FIELDS = {f['name'] for f in BACKTEST_FIELDS if f.get('json_field')}


def _build_sql_where(conditions, param_prefix='cond'):
    """
    将条件列表转为 SQL WHERE 子句（参数化，防注入）
    支持 ext_indicators JSON 字段（自动使用 JSON_EXTRACT）
    支持字段间比较（is_field_compare=True）
    返回: (where_clause_str, params_dict)
    """
    clauses = []
    params = {}
    for i, c in enumerate(conditions):
        field = c['field']
        op = c['op']
        param_key = f"{param_prefix}_{i}"
        
        # 判断是否为字段间比较
        is_field_compare = c.get('is_field_compare', False)
        compare_field = c.get('compare_field')

        # 构建字段表达式
        def _get_field_expr(f):
            if f in _JSON_FIELDS:
                return f"CAST(JSON_EXTRACT(ext_indicators, '$.{f}') AS DOUBLE)"
            return f"`{f}`"
        
        field_expr = _get_field_expr(field)

        if is_field_compare and compare_field:
            # 字段间比较：field op compare_field
            compare_expr = _get_field_expr(compare_field)
            if op == 'between':
                # between 不支持字段间比较，转为普通模式
                clauses.append(f"{field_expr} >= :{param_key}_lo AND {field_expr} <= :{param_key}_hi")
                params[f"{param_key}_lo"] = float(c['value'])
                params[f"{param_key}_hi"] = float(c.get('value2', c['value']))
            elif op == '=':
                clauses.append(f"{field_expr} = {compare_expr}")
            elif op == '!=':
                clauses.append(f"{field_expr} != {compare_expr}")
            else:
                # >, >=, <, <=
                clauses.append(f"{field_expr} {op} {compare_expr}")
        else:
            # 普通条件：field op value
            if op == 'between':
                clauses.append(f"{field_expr} >= :{param_key}_lo AND {field_expr} <= :{param_key}_hi")
                params[f"{param_key}_lo"] = float(c['value'])
                params[f"{param_key}_hi"] = float(c.get('value2', c['value']))
            elif op == '=':
                clauses.append(f"{field_expr} = :{param_key}")
                params[param_key] = float(c['value'])
            elif op == '!=':
                clauses.append(f"{field_expr} != :{param_key}")
                params[param_key] = float(c['value'])
            else:
                # >, >=, <, <=
                clauses.append(f"{field_expr} {op} :{param_key}")
                params[param_key] = float(c['value'])

    return ' AND '.join(clauses), params


def _estimate_max_concurrent(trades):
    """
    估算最大并发交易数（用于资金曲线计算）
    
    基于交易时间窗口重叠计算
    """
    if not trades:
        return 1
    
    # 构建时间区间列表
    intervals = []
    for t in trades:
        # 解析信号时间
        signal_time = t['signal_time']  # '09:30:45' 格式
        duration = t.get('duration_sec', 0)
        
        # 转换为秒
        try:
            h = int(signal_time.split(':')[0])
            m = int(signal_time.split(':')[1])
            s = int(signal_time.split(':')[2])
            start_sec = h * 3600 + m * 60 + s
            end_sec = start_sec + duration
            intervals.append((start_sec, end_sec))
        except:
            continue
    
    if not intervals:
        return 1
    
    # 扫描线算法计算最大重叠数
    events = []
    for start, end in intervals:
        events.append((start, 1))  # 开始事件
        events.append((end, -1))   # 结束事件
    
    events.sort(key=lambda x: (x[0], x[1]))  # 按时间排序，结束事件优先
    
    max_concurrent = 1
    current = 0
    for _, delta in events:
        current += delta
        max_concurrent = max(max_concurrent, current)
    
    return max(1, max_concurrent)


def run_bond_backtest(engine, date, conditions, tp_pct, sl_pct,
                      window_minutes, dedup='first_per_minute',
                      time_start='09:30:00', time_end='15:00:00',
                      price_offset=0.0, offset_mode='fixed',
                      return_calc_method='compound', groups=None):
    """
    执行债券量化回测（两阶段查询）

    Args:
        engine: SQLAlchemy engine（共享引擎）
        date: 日期 YYYYMMDD
        conditions: [{'field', 'op', 'value', 'value2'(optional)}] - 基础条件（AND）
        groups: [{'name', 'mode', 'conditions': [...], 'subgroups': [...]}] 
                - 条件组（组间AND）
                - mode='and': 组内conditions AND
                - mode='or': 子条件组间OR（subgroups内AND）
        tp_pct: 止盈百分比（如0.5表示+0.5%）
        sl_pct: 止损百分比（如0.3表示-0.3%）
        window_minutes: 观察窗口（分钟）
        dedup: 去重模式 'first_per_minute' | 'none'
        time_start: 信号时间范围开始
        time_end: 信号时间范围结束
        price_offset: 价格偏移（元或百分比）
        offset_mode: 偏移模式 'fixed' | 'percent'
        return_calc_method: 总收益计算方式 'compound'(复利) | 'average'(平均) | 'curve'(资金曲线)

    Returns:
        (summary_dict, trades_list)
    """
    groups = groups or []
    
    # ====== 0. 校验 ======
    all_conds = list(conditions) if conditions else []
    for g in groups:
        if g.get('mode') == 'or' and g.get('subgroups'):
            for sg in g['subgroups']:
                all_conds.extend(sg.get('conditions', []))
        else:
            all_conds.extend(g.get('conditions', []))
    
    for c in all_conds:
        if c['field'] not in VALID_FIELDS:
            raise ValueError(f"非法字段: {c['field']}")
        if c['op'] not in VALID_OPS:
            raise ValueError(f"非法操作符: {c['op']}")

    if not conditions and not groups:
        raise ValueError("至少需要一个入场条件或条件组")

    table = f"monitor_zq_sssj_{date}"

    # ====== 阶段1：构建复合WHERE ======
    # 基础条件 AND 条件组A AND 条件组B ...
    # 条件组: mode='and' -> 组内AND
    #         mode='or'  -> 子条件组间OR（子条件组内AND）
    where_parts = []
    params = {'time_start': time_start, 'time_end': time_end}
    param_counter = [0]  # 可变对象用于计数
    
    def _build_where_recursive(conds, prefix):
        if not conds:
            return None, {}
        where, ps = _build_sql_where(conds, param_prefix=f"{prefix}_{param_counter[0]}")
        param_counter[0] += 1
        return where, ps
    
    # 基础条件
    if conditions:
        base_where, base_params = _build_where_recursive(conditions, 'base')
        if base_where:
            where_parts.append(f"({base_where})")
            params.update(base_params)
    
    # 条件组（组间AND）
    for gi, g in enumerate(groups):
        mode = g.get('mode', 'and')
        if mode == 'or' and g.get('subgroups'):
            # OR模式：子条件组间OR
            sub_wheres = []
            for sgi, sg in enumerate(g['subgroups']):
                sg_conds = sg.get('conditions', [])
                if sg_conds:
                    sg_where, sg_params = _build_where_recursive(sg_conds, f'g{gi}s{sgi}')
                    if sg_where:
                        sub_wheres.append(f"({sg_where})")
                        params.update(sg_params)
            if sub_wheres:
                where_parts.append(f"({' OR '.join(sub_wheres)})")
        else:
            # AND模式：组内条件AND
            g_conds = g.get('conditions', [])
            if g_conds:
                g_where, g_params = _build_where_recursive(g_conds, f'g{gi}')
                if g_where:
                    where_parts.append(f"({g_where})")
                    params.update(g_params)
    
    where_clause = ' AND '.join(where_parts) if where_parts else '1=1'

    signal_sql = text(f"""
        SELECT bond_code, bond_name, time, price
        FROM {table}
        WHERE {where_clause}
          AND time >= :time_start AND time <= :time_end
        ORDER BY bond_code, time
    """)

    with engine.connect() as conn:
        df_signals = pd.read_sql(signal_sql, conn, params=params)

    if df_signals.empty:
        return {'total_signals': 0, 'tp_count': 0, 'sl_count': 0,
                'timeout_count': 0, 'win_rate': 0, 'avg_profit_pct': 0,
                'avg_loss_pct': 0, 'profit_factor': 0, 'max_profit_pct': 0,
                'max_loss_pct': 0, 'total_return_pct': 0, 'avg_duration_sec': 0}, []

    # 转换time列为timedelta用于计算（处理 HHMMSS 或 HH:MM:SS 格式）
    time_values = df_signals['time'].astype(str)
    if time_values.str.contains(':').any():
        # 已经是 HH:MM:SS 格式
        df_signals['time_td'] = pd.to_timedelta(time_values)
    else:
        # HHMMSS 格式，需要转换
        df_signals['time_td'] = pd.to_timedelta(
            time_values.str[:2] + ':' + time_values.str[2:4] + ':' + time_values.str[4:6]
        )

    # 去重：每分钟每债券只取第一个信号
    if dedup == 'first_per_minute':
        df_signals['minute_key'] = (
            df_signals['time_td'].dt.components['hours'].astype(str).str.zfill(2) + ':' +
            df_signals['time_td'].dt.components['minutes'].astype(str).str.zfill(2)
        )
        df_signals = df_signals.sort_values('time_td').groupby(['bond_code', 'minute_key']).first().reset_index()

    # ====== 阶段2：查询信号债券的完整价格序列 ======
    signal_codes = df_signals['bond_code'].unique().tolist()
    earliest_time = df_signals['time_td'].min()
    latest_time = df_signals['time_td'].max() + pd.Timedelta(minutes=window_minutes)

    earliest_str = _td_to_str(earliest_time)
    latest_str = _td_to_str(latest_time)

    # 分批查询防止 IN 列表过长
    BATCH_SIZE = 200
    price_dfs = []
    for i in range(0, len(signal_codes), BATCH_SIZE):
        batch_codes = signal_codes[i:i + BATCH_SIZE]
        codes_str = ','.join([f"'{c}'" for c in batch_codes])
        price_sql = text(f"""
            SELECT bond_code, time, price
            FROM {table}
            WHERE bond_code IN ({codes_str})
              AND time >= :earliest AND time <= :latest
            ORDER BY bond_code, time
        """)
        with engine.connect() as conn:
            batch_df = pd.read_sql(price_sql, conn, params={
                'earliest': earliest_str,
                'latest': latest_str,
            })
        price_dfs.append(batch_df)

    df_prices = pd.concat(price_dfs, ignore_index=True) if price_dfs else pd.DataFrame()

    if df_prices.empty:
        return {'total_signals': len(df_signals), 'tp_count': 0, 'sl_count': 0,
                'timeout_count': len(df_signals), 'win_rate': 0, 'avg_profit_pct': 0,
                'avg_loss_pct': 0, 'profit_factor': 0, 'max_profit_pct': 0,
                'max_loss_pct': 0, 'total_return_pct': 0, 'avg_duration_sec': 0}, []

    # 转换time列为timedelta（处理 HHMMSS 或 HH:MM:SS 格式）
    price_time_values = df_prices['time'].astype(str)
    if price_time_values.str.contains(':').any():
        df_prices['time_td'] = pd.to_timedelta(price_time_values)
    else:
        df_prices['time_td'] = pd.to_timedelta(
            price_time_values.str[:2] + ':' + price_time_values.str[2:4] + ':' + price_time_values.str[4:6]
        )

    # ====== 阶段3：逐信号判定止盈止损 ======
    window_td = pd.Timedelta(minutes=window_minutes)
    trades = []

    # 按bond_code分组价格数据
    price_grouped = {}
    for code, group in df_prices.groupby('bond_code'):
        sorted_group = group.sort_values('time_td')
        price_grouped[code] = (sorted_group['time_td'].values, sorted_group['price'].values.astype(float))

    for _, sig in df_signals.iterrows():
        code = sig['bond_code']
        entry_time = sig['time_td']
        signal_price = float(sig['price'])

        if signal_price <= 0:
            continue

        # 应用价格偏移计算实际入场价
        if offset_mode == 'percent':
            entry_price = signal_price * (1 + price_offset / 100)
        else:
            entry_price = signal_price + price_offset

        if entry_price <= 0:
            continue

        tp_price = entry_price * (1 + tp_pct / 100)
        sl_price = entry_price * (1 - sl_pct / 100)
        deadline = entry_time + window_td

        # 获取该bond在信号后的价格序列
        if code not in price_grouped:
            continue

        all_times, all_prices = price_grouped[code]

        # 筛选 entry_time < time <= deadline
        mask = (all_times > entry_time) & (all_times <= deadline)
        future_times = all_times[mask]
        future_prices = all_prices[mask]

        exit_type = 'timeout'
        exit_price = entry_price
        exit_time = entry_time
        max_price = entry_price
        min_price = entry_price

        if len(future_prices) > 0:
            max_price = float(np.max(future_prices))
            min_price = float(np.min(future_prices))

            # 向量化查找首次触达
            tp_hits = np.where(future_prices >= tp_price)[0]
            sl_hits = np.where(future_prices <= sl_price)[0]

            tp_idx = tp_hits[0] if len(tp_hits) > 0 else len(future_prices) + 1
            sl_idx = sl_hits[0] if len(sl_hits) > 0 else len(future_prices) + 1

            if tp_idx <= sl_idx and tp_idx < len(future_prices) + 1:
                exit_type = 'tp'
                exit_price = float(future_prices[tp_idx])
                exit_time = future_times[tp_idx]
            elif sl_idx < tp_idx and sl_idx < len(future_prices) + 1:
                exit_type = 'sl'
                exit_price = float(future_prices[sl_idx])
                exit_time = future_times[sl_idx]
            else:
                exit_price = float(future_prices[-1])
                exit_time = future_times[-1]

        profit_pct = round((exit_price - entry_price) / entry_price * 100, 4)

        # 计算持续时间
        duration_td = exit_time - entry_time
        duration_sec = int(pd.Timedelta(duration_td).total_seconds()) if exit_time != entry_time else 0

        trades.append({
            'bond_code': code,
            'bond_name': sig.get('bond_name', ''),
            'signal_time': _td_to_str(entry_time),
            'entry_price': round(entry_price, 3),
            'exit_price': round(exit_price, 3),
            'exit_time': _td_to_str(exit_time),
            'exit_type': exit_type,
            'profit_pct': profit_pct,
            'duration_sec': duration_sec,
            'max_price': round(max_price, 3),
            'min_price': round(min_price, 3),
        })

    # ====== 统计汇总 ======
    if not trades:
        return {'total_signals': 0, 'tp_count': 0, 'sl_count': 0,
                'timeout_count': 0, 'win_rate': 0, 'avg_profit_pct': 0,
                'avg_loss_pct': 0, 'profit_factor': 0, 'max_profit_pct': 0,
                'max_loss_pct': 0, 'total_return_pct': 0, 'avg_duration_sec': 0}, []

    tp_trades = [t for t in trades if t['exit_type'] == 'tp']
    sl_trades = [t for t in trades if t['exit_type'] == 'sl']
    timeout_trades = [t for t in trades if t['exit_type'] == 'timeout']
    all_profits = [t['profit_pct'] for t in trades]

    avg_profit = float(np.mean([t['profit_pct'] for t in tp_trades])) if tp_trades else 0
    avg_loss = float(np.mean([t['profit_pct'] for t in sl_trades])) if sl_trades else 0

    # ====== 总收益计算（支持三种方式）======
    # 使用传入的计算方式参数，默认复利
    
    if return_calc_method == 'compound':
        # 方案B：复利计算（默认）
        # 假设每笔交易使用全部资金，收益复利累积
        total_return_multiplier = 1.0
        for profit in all_profits:
            total_return_multiplier *= (1 + profit / 100)
        total_return_pct = (total_return_multiplier - 1) * 100
    elif return_calc_method == 'average':
        # 方案A：等权重平均
        # 假设每笔交易分配相等资金，总收益为平均收益
        total_return_pct = np.mean(all_profits) if all_profits else 0
    elif return_calc_method == 'curve':
        # 方案C：资金曲线法
        # 模拟实际资金曲线，假设初始资金100万，每笔交易分配固定金额
        initial_capital = 1000000.0
        # 估算最大并发交易数（基于时间窗口重叠）
        max_concurrent = _estimate_max_concurrent(trades) if trades else 1
        trade_capital = initial_capital / max(1, max_concurrent)
        
        capital = initial_capital
        for trade in trades:
            profit_amount = trade_capital * trade['profit_pct'] / 100
            capital += profit_amount
        total_return_pct = (capital - initial_capital) / initial_capital * 100
    else:
        # 默认复利计算
        total_return_multiplier = 1.0
        for profit in all_profits:
            total_return_multiplier *= (1 + profit / 100)
        total_return_pct = (total_return_multiplier - 1) * 100

    summary = {
        'total_signals': len(trades),
        'tp_count': len(tp_trades),
        'sl_count': len(sl_trades),
        'timeout_count': len(timeout_trades),
        'win_rate': round(len(tp_trades) / len(trades) * 100, 2),
        'avg_profit_pct': round(avg_profit, 4),
        'avg_loss_pct': round(avg_loss, 4),
        'profit_factor': round(abs(avg_profit / avg_loss), 2) if avg_loss != 0 else 999,
        'max_profit_pct': round(max(all_profits), 4) if all_profits else 0,
        'max_loss_pct': round(min(all_profits), 4) if all_profits else 0,
        'total_return_pct': round(total_return_pct, 2),
        'return_calc_method': return_calc_method,  # 返回使用的计算方式
        'avg_duration_sec': int(np.mean([t['duration_sec'] for t in trades])),
    }

    return summary, trades


def run_bond_backtest_timeline(engine, date, conditions, tp_pct, sl_pct,
                                window_minutes, dedup='first_per_minute',
                                time_start='09:30:00', time_end='15:00:00',
                                price_offset=0.0, offset_mode='fixed',
                                initial_capital=1000000.0, groups=None):
    """
    债券量化回测 - 时间线模式
    
    核心逻辑：信号串行触发，前一个出场后才能触发下一个
    更接近真实交易（资金有限，不能同时持有多个仓位）
    
    Args:
        engine: SQLAlchemy engine
        date: 日期 YYYYMMDD
        conditions: 入场条件（AND）
        groups: 条件组（组内AND，组间OR）
        tp_pct: 止盈百分比
        sl_pct: 止损百分比
        window_minutes: 最大观察窗口
        dedup: 去重模式
        time_start/time_end: 信号时间范围
        price_offset: 价格偏移
        offset_mode: 偏移模式
        initial_capital: 初始资金
        
    Returns:
        (summary_dict, trades_list)
    """
    groups = groups or []
    
    # ====== 阶段1：构建复合WHERE ======
    # 基础条件 AND 条件组A AND 条件组B ...
    table = f"monitor_zq_sssj_{date}"
    
    where_parts = []
    params = {'time_start': time_start.replace(':', ''), 'time_end': time_end.replace(':', '')}
    param_counter = [0]
    
    def _build_where_recursive(conds, prefix):
        if not conds:
            return None, {}
        where, ps = _build_sql_where(conds, param_prefix=f"{prefix}_{param_counter[0]}")
        param_counter[0] += 1
        return where, ps
    
    # 基础条件
    if conditions:
        base_where, base_params = _build_where_recursive(conditions, 'base')
        if base_where:
            where_parts.append(f"({base_where})")
            params.update(base_params)
    
    # 条件组（组间AND）
    for gi, g in enumerate(groups):
        mode = g.get('mode', 'and')
        if mode == 'or' and g.get('subgroups'):
            # OR模式：子条件组间OR
            sub_wheres = []
            for sgi, sg in enumerate(g['subgroups']):
                sg_conds = sg.get('conditions', [])
                if sg_conds:
                    sg_where, sg_params = _build_where_recursive(sg_conds, f'g{gi}s{sgi}')
                    if sg_where:
                        sub_wheres.append(f"({sg_where})")
                        params.update(sg_params)
            if sub_wheres:
                where_parts.append(f"({' OR '.join(sub_wheres)})")
        else:
            # AND模式：组内条件AND
            g_conds = g.get('conditions', [])
            if g_conds:
                g_where, g_params = _build_where_recursive(g_conds, f'g{gi}')
                if g_where:
                    where_parts.append(f"({g_where})")
                    params.update(g_params)
    
    where_clause = ' AND '.join(where_parts) if where_parts else '1=1'
    time_where = " AND time >= :time_start AND time <= :time_end"
    
    sql_signals = text(f"""
        SELECT bond_code, bond_name, time, price, change_pct, amount
        FROM {table}
        WHERE {where_clause} {time_where}
        ORDER BY time, bond_code
    """)
    
    with engine.connect() as conn:
        df_signals = pd.read_sql(sql_signals, conn, params=params)
    
    if df_signals.empty:
        return {'total_signals': 0, 'skipped_signals': 0, 'utilization_rate': 0,
                'total_return_pct': 0, 'max_drawdown': 0}, []
    
    # 去重处理
    if dedup == 'first_per_minute':
        df_signals['minute'] = df_signals['time'].str[:4]
        df_signals = df_signals.drop_duplicates(subset=['bond_code', 'minute'], keep='first')
    
    # ====== 阶段2：预加载所有价格数据 ======
    all_codes = df_signals['bond_code'].unique().tolist()
    price_grouped = {}
    
    for code in all_codes:
        sql_prices = text(f"""
            SELECT time, price FROM {table}
            WHERE bond_code = :code AND time >= :time_start AND time <= :time_end
            ORDER BY time
        """)
        with engine.connect() as conn:
            df_prices = pd.read_sql(sql_prices, conn, 
                                    params={'code': code, 'time_start': params['time_start'], 
                                           'time_end': params['time_end']})
        if not df_prices.empty:
            # 处理时间格式：可能是 HHMMSS 或 HH:MM:SS
            time_values = df_prices['time'].astype(str)
            if time_values.str.contains(':').any():
                # 已经是 HH:MM:SS 格式
                times = pd.to_timedelta(time_values)
            else:
                # HHMMSS 格式，需要转换
                times = pd.to_timedelta(time_values.str[:2] + ':' + 
                                       time_values.str[2:4] + ':' + 
                                       time_values.str[4:6])
            price_grouped[code] = (times.values, df_prices['price'].values)
    
    # ====== 阶段3：时间线遍历 ======
    # 验证时间格式
    try:
        window_td = pd.Timedelta(minutes=window_minutes)
        market_end = pd.Timedelta(time_end)
        current_time = pd.Timedelta(time_start)
    except Exception as e:
        raise ValueError(f"时间格式错误: time_start={time_start}, time_end={time_end}, error={e}")
    
    if current_time >= market_end:
        raise ValueError(f"时间范围错误: time_start ({time_start}) 必须早于 time_end ({time_end})")
    
    trades = []
    skipped_signals = 0
    capital = initial_capital
    capital_history = [(current_time, capital)]  # 用于计算回撤
    
    for _, sig in df_signals.iterrows():
        code = sig['bond_code']
        signal_time_str = sig['time']
        # 处理时间格式：可能是 HHMMSS 或 HH:MM:SS
        if ':' in signal_time_str:
            # 已经是 HH:MM:SS 格式
            signal_time = pd.Timedelta(signal_time_str)
        else:
            # HHMMSS 格式，需要转换
            signal_time = pd.Timedelta(
                signal_time_str[:2] + ':' + signal_time_str[2:4] + ':' + signal_time_str[4:6]
            )
        signal_price = float(sig['price'])
        
        # 时间线检查：信号必须在当前时间之后
        if signal_time < current_time:
            skipped_signals += 1
            continue
        
        # 应用价格偏移
        if offset_mode == 'percent':
            entry_price = signal_price * (1 + price_offset / 100)
        else:
            entry_price = signal_price + price_offset
        
        if entry_price <= 0:
            continue
        
        tp_price = entry_price * (1 + tp_pct / 100)
        sl_price = entry_price * (1 - sl_pct / 100)
        deadline = signal_time + window_td
        actual_deadline = min(deadline, market_end)
        
        # 获取该债券后续价格序列
        if code not in price_grouped:
            continue
        
        all_times, all_prices = price_grouped[code]
        
        # 筛选 signal_time < time <= actual_deadline
        mask = (all_times > signal_time) & (all_times <= actual_deadline)
        future_times = all_times[mask]
        future_prices = all_prices[mask]
        
        if len(future_prices) == 0:
            skipped_signals += 1
            continue
        
        # 查找出场点
        exit_type = 'timeout'
        exit_price = future_prices[-1]
        exit_time = future_times[-1]
        
        # 向量化查找首次触达
        tp_hits = np.where(future_prices >= tp_price)[0]
        sl_hits = np.where(future_prices <= sl_price)[0]
        
        tp_idx = tp_hits[0] if len(tp_hits) > 0 else len(future_prices) + 1
        sl_idx = sl_hits[0] if len(sl_hits) > 0 else len(future_prices) + 1
        
        if tp_idx <= sl_idx and tp_idx < len(future_prices) + 1:
            exit_type = 'tp'
            exit_price = float(future_prices[tp_idx])
            exit_time = future_times[tp_idx]
        elif sl_idx < tp_idx and sl_idx < len(future_prices) + 1:
            exit_type = 'sl'
            exit_price = float(future_prices[sl_idx])
            exit_time = future_times[sl_idx]
        
        # 计算收益
        profit_pct = (exit_price - entry_price) / entry_price * 100
        profit_amount = capital * profit_pct / 100
        capital_before = capital
        capital += profit_amount
        
        # 更新时间线
        current_time = exit_time
        capital_history.append((current_time, capital))
        
        # 记录交易
        trades.append({
            'bond_code': code,
            'bond_name': sig.get('bond_name', ''),
            'signal_time': _td_to_str(signal_time),
            'entry_time': _td_to_str(signal_time),
            'exit_time': _td_to_str(exit_time),
            'entry_price': round(entry_price, 3),
            'exit_price': round(exit_price, 3),
            'exit_type': exit_type,
            'profit_pct': round(profit_pct, 4),
            'profit_amount': round(profit_amount, 2),
            'capital_before': round(capital_before, 2),
            'capital_after': round(capital, 2),
            'duration_sec': int((exit_time - signal_time).total_seconds()),
        })
    
    # ====== 阶段4：统计汇总 ======
    if not trades:
        return {'total_signals': 0, 'skipped_signals': skipped_signals,
                'utilization_rate': 0, 'total_return_pct': 0, 'max_drawdown': 0}, []
    
    tp_trades = [t for t in trades if t['exit_type'] == 'tp']
    sl_trades = [t for t in trades if t['exit_type'] == 'sl']
    timeout_trades = [t for t in trades if t['exit_type'] == 'timeout']
    
    # 计算资金利用率（持仓时间 / 总交易时间）
    total_trade_duration = sum(t['duration_sec'] for t in trades)
    try:
        market_duration = (pd.Timedelta(time_end) - pd.Timedelta(time_start)).total_seconds()
    except Exception as e:
        print(f"[ERROR] market_duration calculation failed: time_start={time_start}, time_end={time_end}, error={e}")
        market_duration = 0
    utilization_rate = round(total_trade_duration / market_duration * 100, 2) if market_duration > 0 else 0
    
    # 计算最大回撤
    max_drawdown = 0
    peak_capital = initial_capital
    for _, cap in capital_history:
        if cap > peak_capital:
            peak_capital = cap
        drawdown = (peak_capital - cap) / peak_capital * 100
        max_drawdown = max(max_drawdown, drawdown)
    
    # 总收益（基于最终资金）
    total_return_pct = round((capital - initial_capital) / initial_capital * 100, 2)
    
    # 计算盈亏比（平均盈利 / 平均亏损绝对值）
    avg_profit = np.mean([t['profit_pct'] for t in tp_trades]) if tp_trades else 0
    avg_loss = abs(np.mean([t['profit_pct'] for t in sl_trades])) if sl_trades else 0
    profit_factor = round(avg_profit / avg_loss, 2) if avg_loss > 0 else (999 if avg_profit > 0 else 0)
    
    summary = {
        'mode': 'timeline',
        'total_signals': len(trades),
        'skipped_signals': skipped_signals,
        'tp_count': len(tp_trades),
        'sl_count': len(sl_trades),
        'timeout_count': len(timeout_trades),
        'win_rate': round(len(tp_trades) / len(trades) * 100, 2),
        'avg_profit_pct': round(avg_profit, 4),
        'avg_loss_pct': round(avg_loss, 4),
        'profit_factor': profit_factor,
        'total_return_pct': total_return_pct,
        'final_capital': round(capital, 2),
        'initial_capital': initial_capital,
        'utilization_rate': utilization_rate,
        'max_drawdown': round(max_drawdown, 2),
        'avg_duration_sec': int(np.mean([t['duration_sec'] for t in trades])),
    }
    
    return summary, trades


# ====== 区间回测功能 ======

def _format_date_for_db(date_str: str) -> str:
    """将 20260701 格式转换为 2026-07-01 格式"""
    if len(date_str) == 8 and '-' not in date_str:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def get_trade_dates(engine, date_start: str, date_end: str) -> list:
    """
    从 data_jyrl 获取区间内的交易日历
    
    Args:
        engine: 数据库引擎
        date_start: 开始日期 '20260701' 或 '2026-07-01'
        date_end: 结束日期 '20260710' 或 '2026-07-10'
        
    Returns:
        交易日期列表 ['20260701', '20260703', ...] (无横线格式)
    """
    from sqlalchemy import text
    
    # 转换日期格式为数据库格式 (带横线)
    db_start = _format_date_for_db(date_start)
    db_end = _format_date_for_db(date_end)
    
    sql = text("""
        SELECT DISTINCT trade_date as date 
        FROM data_jyrl 
        WHERE trade_date >= :date_start AND trade_date <= :date_end
          AND trade_status = 1
        ORDER BY trade_date
    """)
    
    try:
        print(f"[get_trade_dates] Query: {db_start} ~ {db_end} (from {date_start} ~ {date_end})")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={
                'date_start': db_start,
                'date_end': db_end
            })
        
        # 转换回无横线格式
        if not df.empty:
            dates = [str(d).replace('-', '') for d in df['date'].tolist()]
        else:
            dates = []
        print(f"[get_trade_dates] Found {len(dates)} dates: {dates[:5]}...")
        return dates
    except Exception as e:
        print(f"[get_trade_dates] Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def run_bond_backtest_range(engine, date_start: str, date_end: str, conditions: list,
                            tp_pct: float, sl_pct: float, window_minutes: int,
                            dedup: str = 'first_per_minute',
                            time_start: str = '09:30:00', time_end: str = '15:00:00',
                            price_offset: float = 0.0, offset_mode: str = 'fixed',
                            timeline_mode: bool = False, initial_capital: float = 1000000.0,
                            return_calc_method: str = 'compound'):
    """
    债券量化回测 - 区间回测主入口
    
    支持多交易日并行回测，自动汇总结果
    
    Args:
        engine: 数据库引擎
        date_start: 开始日期 '20260701'
        date_end: 结束日期 '20260710'
        conditions: 入场条件列表
        tp_pct: 止盈百分比
        sl_pct: 止损百分比
        window_minutes: 持有窗口（分钟）
        dedup: 去重模式
        time_start: 日内开始时间
        time_end: 日内结束时间
        price_offset: 价格偏移
        offset_mode: 偏移模式
        timeline_mode: 是否使用时间线模式
        initial_capital: 初始资金
        return_calc_method: 收益计算方式
        
    Returns:
        (summary, trades, daily_results)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # 1. 获取交易日历
    trade_dates = get_trade_dates(engine, date_start, date_end)
    
    if not trade_dates:
        raise ValueError(f"区间内无交易日: {date_start} ~ {date_end}")
    
    if len(trade_dates) > 30:
        raise ValueError(f"回测区间超过30天限制: {len(trade_dates)}天")
    
    print(f"[RangeBacktest] 交易日: {len(trade_dates)}天, 从 {trade_dates[0]} 到 {trade_dates[-1]}")
    
    # 2. 定义单日回测包装函数
    def _run_single_day(date):
        """执行单日回测"""
        try:
            if timeline_mode:
                summary, trades = run_bond_backtest_timeline(
                    engine=engine,
                    date=date,
                    conditions=conditions,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    window_minutes=window_minutes,
                    dedup=dedup,
                    time_start=time_start,
                    time_end=time_end,
                    price_offset=price_offset,
                    offset_mode=offset_mode,
                    initial_capital=initial_capital
                )
            else:
                summary, trades = run_bond_backtest(
                    engine=engine,
                    date=date,
                    conditions=conditions,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    window_minutes=window_minutes,
                    dedup=dedup,
                    time_start=time_start,
                    time_end=time_end,
                    price_offset=price_offset,
                    offset_mode=offset_mode,
                    return_calc_method=return_calc_method
                )
            
            return {
                'date': date,
                'summary': summary,
                'trades': trades,
                'success': True
            }
        except Exception as e:
            print(f"[RangeBacktest] 回测失败 {date}: {e}")
            return {
                'date': date,
                'summary': {'total_signals': 0, 'tp_count': 0, 'sl_count': 0, 'timeout_count': 0},
                'trades': [],
                'success': False,
                'error': str(e)
            }
    
    # 3. 并行执行多日回测
    daily_results = []
    max_workers = min(4, len(trade_dates))  # 最多4线程
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_single_day, date): date for date in trade_dates}
        
        for future in as_completed(futures):
            result = future.result()
            daily_results.append(result)
    
    # 4. 按日期排序
    daily_results.sort(key=lambda x: x['date'])
    
    # 5. 汇总结果
    summary = aggregate_range_results(daily_results, timeline_mode, initial_capital)
    
    # 6. 合并所有交易
    all_trades = []
    for dr in daily_results:
        for t in dr['trades']:
            t['date'] = dr['date']  # 添加日期标记
            all_trades.append(t)
    
    return summary, all_trades, daily_results


def aggregate_range_results(daily_results: list, timeline_mode: bool, initial_capital: float) -> dict:
    """
    汇总多日回测结果
    
    Args:
        daily_results: 每日回测结果列表
        timeline_mode: 是否时间线模式
        initial_capital: 初始资金
        
    Returns:
        汇总后的统计字典
    """
    valid_results = [r for r in daily_results if r.get('success', True)]
    
    if not valid_results:
        return {
            'mode': 'range',
            'date_start': daily_results[0]['date'] if daily_results else '',
            'date_end': daily_results[-1]['date'] if daily_results else '',
            'trade_days': len(daily_results),
            'total_signals': 0,
            'avg_daily_signals': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_return_pct': 0,
            'return_volatility': 0,
            'max_consecutive_loss_days': 0,
            'daily_results': []
        }
    
    # 基础统计
    total_signals = sum(r['summary'].get('total_signals', 0) for r in valid_results)
    total_tp = sum(r['summary'].get('tp_count', 0) for r in valid_results)
    total_sl = sum(r['summary'].get('sl_count', 0) for r in valid_results)
    total_timeout = sum(r['summary'].get('timeout_count', 0) for r in valid_results)
    
    # 每日收益
    daily_returns = []
    for r in valid_results:
        s = r['summary']
        daily_returns.append(s.get('total_return_pct', 0))
    
    # 连续亏损天数
    consecutive_losses = 0
    max_consecutive_losses = 0
    for ret in daily_returns:
        if ret < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
    
    # 计算盈亏比
    avg_profit_list = [r['summary'].get('avg_profit_pct', 0) for r in valid_results if r['summary'].get('tp_count', 0) > 0]
    avg_loss_list = [abs(r['summary'].get('avg_loss_pct', 0)) for r in valid_results if r['summary'].get('sl_count', 0) > 0]
    
    avg_profit = np.mean(avg_profit_list) if avg_profit_list else 0
    avg_loss = np.mean(avg_loss_list) if avg_loss_list else 0
    profit_factor = round(avg_profit / avg_loss, 2) if avg_loss > 0 else (999 if avg_profit > 0 else 0)
    
    # 计算平均耗时（所有交易的平均持有时间）
    all_durations = []
    for r in valid_results:
        for t in r.get('trades', []):
            if 'duration_sec' in t:
                all_durations.append(t['duration_sec'])
    avg_duration_sec = int(np.mean(all_durations)) if all_durations else 0
    
    # 汇总
    return {
        'mode': 'range',
        'date_start': valid_results[0]['date'],
        'date_end': valid_results[-1]['date'],
        'trade_days': len(valid_results),
        'total_signals': total_signals,
        'avg_daily_signals': round(total_signals / len(valid_results), 2),
        'tp_count': total_tp,
        'sl_count': total_sl,
        'timeout_count': total_timeout,
        'win_rate': round(total_tp / total_signals * 100, 2) if total_signals > 0 else 0,
        'avg_profit_pct': round(avg_profit, 4),
        'avg_loss_pct': round(avg_loss, 4),
        'profit_factor': profit_factor,
        'total_return_pct': round(sum(daily_returns), 2),
        'avg_daily_return': round(np.mean(daily_returns), 2),
        'return_volatility': round(np.std(daily_returns), 2) if len(daily_returns) > 1 else 0,
        'max_consecutive_loss_days': max_consecutive_losses,
        'avg_duration_sec': avg_duration_sec,
        'daily_results': [
            {
                'date': r['date'],
                'total_signals': r['summary'].get('total_signals', 0),
                'tp_count': r['summary'].get('tp_count', 0),
                'sl_count': r['summary'].get('sl_count', 0),
                'timeout_count': r['summary'].get('timeout_count', 0),
                'daily_return_pct': r['summary'].get('total_return_pct', 0)
            } for r in valid_results
        ]
    }
