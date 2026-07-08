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
    {'name': 'is_body_up', 'label': '实体阳', 'group': '形态类', 'type': 'int'},
    {'name': 'is_body_down', 'label': '实体阴', 'group': '形态类', 'type': 'int'},
    {'name': 'is_body_flat', 'label': '实体平', 'group': '形态类', 'type': 'int'},
]

VALID_FIELDS = {f['name'] for f in BACKTEST_FIELDS}
VALID_OPS = {'>', '>=', '<', '<=', '=', '!=', 'between'}


def _build_sql_where(conditions):
    """
    将条件列表转为 SQL WHERE 子句（参数化，防注入）
    返回: (where_clause_str, params_dict)
    """
    clauses = []
    params = {}
    for i, c in enumerate(conditions):
        field = c['field']
        op = c['op']
        param_key = f"cond_{i}"

        if op == 'between':
            clauses.append(f"`{field}` >= :{param_key}_lo AND `{field}` <= :{param_key}_hi")
            params[f"{param_key}_lo"] = float(c['value'])
            params[f"{param_key}_hi"] = float(c.get('value2', c['value']))
        elif op == '=':
            clauses.append(f"`{field}` = :{param_key}")
            params[param_key] = float(c['value'])
        elif op == '!=':
            clauses.append(f"`{field}` != :{param_key}")
            params[param_key] = float(c['value'])
        else:
            # >, >=, <, <=
            clauses.append(f"`{field}` {op} :{param_key}")
            params[param_key] = float(c['value'])

    return ' AND '.join(clauses), params


def run_bond_backtest(engine, date, conditions, tp_pct, sl_pct,
                      window_minutes, dedup='first_per_minute',
                      time_start='09:30:00', time_end='15:00:00'):
    """
    执行债券量化回测（两阶段查询）

    Args:
        engine: SQLAlchemy engine（共享引擎）
        date: 日期 YYYYMMDD
        conditions: [{'field', 'op', 'value', 'value2'(optional)}]
        tp_pct: 止盈百分比（如0.5表示+0.5%）
        sl_pct: 止损百分比（如0.3表示-0.3%）
        window_minutes: 观察窗口（分钟）
        dedup: 去重模式 'first_per_minute' | 'none'
        time_start: 信号时间范围开始
        time_end: 信号时间范围结束

    Returns:
        (summary_dict, trades_list)
    """

    # ====== 0. 校验 ======
    for c in conditions:
        if c['field'] not in VALID_FIELDS:
            raise ValueError(f"非法字段: {c['field']}")
        if c['op'] not in VALID_OPS:
            raise ValueError(f"非法操作符: {c['op']}")

    if not conditions:
        raise ValueError("至少需要一个入场条件")

    table = f"monitor_zq_sssj_{date}"

    # ====== 阶段1：条件下推 → 获取信号点 ======
    where_clause, params = _build_sql_where(conditions)
    params['time_start'] = time_start
    params['time_end'] = time_end

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

    # 转换time列为timedelta用于计算
    df_signals['time_td'] = pd.to_timedelta(df_signals['time'].astype(str))

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

    # 格式化时间为 HH:MM:SS
    def _td_to_str(td):
        total_sec = int(td.total_seconds())
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

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

    df_prices['time_td'] = pd.to_timedelta(df_prices['time'].astype(str))

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
        entry_price = float(sig['price'])

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
            'exit_time': _td_to_str(pd.Timedelta(exit_time)),
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
        'total_return_pct': round(sum(all_profits), 2),
        'avg_duration_sec': int(np.mean([t['duration_sec'] for t in trades])),
    }

    return summary, trades
