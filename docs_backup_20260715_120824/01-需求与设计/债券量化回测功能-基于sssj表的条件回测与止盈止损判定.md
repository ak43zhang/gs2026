# 债券量化回测功能 — 基于sssj表的条件回测与止盈止损判定

## 文档信息
- **创建日期**: 2026-07-08
- **功能位置**: 分析中心 → 回溯分析 下方
- **数据源**: `monitor_zq_sssj_{date}` 表

---

## 一、需求概述

选择某天的债券sssj表，配置入场条件（支持sssj表所有字段，动态增删），执行回测后输出：
1. 命中信号清单（满足条件的债券+时间点）
2. 每笔信号在N分钟内的止盈/止损判定结果
3. 整体统计（胜率、盈亏比、总收益等）

---

## 二、核心数据流（两阶段查询）

### 关键设计：条件筛选与止盈止损判定是两次独立查询

```
┌─────────────────────────────────────────────────────────────────────┐
│                        第一阶段：信号筛选                              │
│                                                                     │
│  SQL条件下推 → 获取满足入场条件的 tick（信号点）                        │
│                                                                     │
│  SELECT bond_code, bond_name, time, price                           │
│  FROM monitor_zq_sssj_20260708                                      │
│  WHERE min1_change_pct > 0.2                                        │
│    AND min1_change_pct < 0.8                                        │
│    AND min1_amount > 10000000                                       │
│    AND time >= '09:30:00' AND time <= '15:00:00'                    │
│                                                                     │
│  结果：命中信号列表（几十~几百条）                                      │
│  内容：哪些债券、在什么时间点、以什么价格触发了入场条件                    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ 提取：bond_codes[] + time范围
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     第二阶段：止盈止损判定                              │
│                                                                     │
│  根据信号点的bond_code列表 + 时间窗口，查询这些债券的全量价格数据         │
│                                                                     │
│  SELECT bond_code, time, price                                      │
│  FROM monitor_zq_sssj_20260708                                      │
│  WHERE bond_code IN ('123456','789012',...)      ← 信号中的债券       │
│    AND time >= '09:32:06'                        ← 最早信号时间       │
│    AND time <= '15:05:00'                        ← 最晚信号+窗口      │
│  ORDER BY bond_code, time                                           │
│                                                                     │
│  结果：信号债券在观察窗口内的完整价格序列（几千~几万条）                   │
│  用途：逐tick扫描判定止盈/止损/超时                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     第三阶段：逐信号判定                               │
│                                                                     │
│  对每个信号点：                                                       │
│    entry_price = 信号时刻价格                                         │
│    tp_price = entry_price × (1 + 止盈%)                              │
│    sl_price = entry_price × (1 - 止损%)                              │
│                                                                     │
│    从信号时刻起，逐tick扫描该bond后续N分钟内价格：                       │
│      if price >= tp_price → 止盈命中（先到），记录盈利，退出              │
│      if price <= sl_price → 止损命中（先到），记录亏损，退出              │
│      if 超过N分钟         → 超时，按末tick价格计算浮盈/浮亏              │
│                                                                     │
│  关键：逐tick遍历保证时间顺序 → 谁先到谁生效                            │
└─────────────────────────────────────────────────────────────────────┘
```

### 为什么分两阶段

| 对比 | 单次全量加载（旧方案） | 两阶段查询（本方案） |
|------|---------------------|-------------------|
| 数据量 | 150万行全部加载 | 阶段1: 几百行 + 阶段2: 几万行 |
| 耗时 | 5-10秒 | < 2秒 |
| 内存 | ~500MB | ~20MB |
| SQL优化 | 无法利用索引 | 条件下推 + IN查询，命中索引 |

---

## 三、sssj表可用字段

| 字段名 | 中文名 | 类型 | 分组 |
|--------|--------|------|------|
| price | 现价 | float | 价格类 |
| open | 开盘价 | float | 价格类 |
| high | 最高价 | float | 价格类 |
| low | 最低价 | float | 价格类 |
| pre_close | 昨收 | float | 价格类 |
| change | 涨跌额 | float | 涨跌类 |
| change_pct | 涨跌幅(%) | float | 涨跌类 |
| volume | 成交量 | float | 成交类 |
| amount | 成交金额 | float | 成交类 |
| min1_change_pct | 1分钟涨幅(%) | float | 1分钟类 |
| min1_amount | 1分钟金额 | float | 1分钟类 |
| is_body_up | 实体阳 | int(0/1) | 形态类 |
| is_body_down | 实体阴 | int(0/1) | 形态类 |
| is_body_flat | 实体平 | int(0/1) | 形态类 |

> 扩展方式：在 `BACKTEST_FIELDS` 列表追加字段定义即可，前端自动渲染。

---

## 四、API设计

### 4.1 获取可用字段

**GET `/api/monitor/backtest/bond/fields`**

```json
{
  "success": true,
  "fields": [
    {"name": "price", "label": "现价", "group": "价格类", "type": "float"},
    {"name": "change_pct", "label": "涨跌幅(%)", "group": "涨跌类", "type": "float"},
    {"name": "min1_change_pct", "label": "1分钟涨幅(%)", "group": "1分钟类", "type": "float"},
    {"name": "min1_amount", "label": "1分钟金额", "group": "成交类", "type": "float"},
    {"name": "is_body_up", "label": "实体阳", "group": "形态类", "type": "int"}
  ]
}
```

### 4.2 执行回测

**POST `/api/monitor/backtest/bond`**

请求：
```json
{
  "date": "20260708",
  "conditions": [
    {"field": "min1_change_pct", "op": ">", "value": 0.2},
    {"field": "min1_change_pct", "op": "<", "value": 0.8},
    {"field": "min1_amount", "op": ">", "value": 10000000}
  ],
  "dedup": "first_per_minute",
  "take_profit_pct": 0.5,
  "stop_loss_pct": 0.3,
  "window_minutes": 5,
  "time_start": "09:30:00",
  "time_end": "15:00:00"
}
```

响应：
```json
{
  "success": true,
  "summary": {
    "total_signals": 86,
    "tp_count": 52,
    "sl_count": 18,
    "timeout_count": 16,
    "win_rate": 60.47,
    "avg_profit_pct": 0.35,
    "avg_loss_pct": -0.28,
    "profit_factor": 2.14,
    "max_profit_pct": 1.2,
    "max_loss_pct": -0.3,
    "total_return_pct": 12.8,
    "avg_duration_sec": 98
  },
  "trades": [
    {
      "bond_code": "123456",
      "bond_name": "XX转债",
      "signal_time": "09:32:06",
      "entry_price": 128.50,
      "exit_price": 129.14,
      "exit_time": "09:34:18",
      "exit_type": "tp",
      "profit_pct": 0.50,
      "duration_sec": 132,
      "max_price": 129.20,
      "min_price": 128.35
    }
  ]
}
```

---

## 五、后端引擎实现

### 5.1 文件结构

```
dashboard2/
├── services/
│   └── backtest_bond.py    ← 核心引擎（纯计算，无Flask依赖）
└── routes/
    └── monitor.py          ← 新增2个API路由
```

### 5.2 核心引擎 `backtest_bond.py`

```python
"""
债券量化回测引擎

两阶段查询策略：
  阶段1：条件下推SQL → 获取信号点（几十~几百条）
  阶段2：按信号bond_code + 时间窗口 → 获取价格序列（几千~几万条）
  阶段3：逐信号逐tick判定止盈/止损/超时
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from sqlalchemy import text


# ====== 字段配置（扩展点）======
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
            params[f"{param_key}_hi"] = float(c['value2'])
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
                'timeout_count': 0, 'win_rate': 0}, []

    # 去重：每分钟每债券只取第一个信号
    df_signals['time_td'] = pd.to_timedelta(df_signals['time'].astype(str))
    if dedup == 'first_per_minute':
        df_signals['minute_key'] = df_signals['time_td'].dt.components['hours'].astype(str).str.zfill(2) + ':' + \
                                   df_signals['time_td'].dt.components['minutes'].astype(str).str.zfill(2)
        df_signals = df_signals.groupby(['bond_code', 'minute_key']).first().reset_index()

    # ====== 阶段2：查询信号债券的完整价格序列 ======
    signal_codes = df_signals['bond_code'].unique().tolist()
    earliest_time = df_signals['time_td'].min()
    latest_time = df_signals['time_td'].max() + pd.Timedelta(minutes=window_minutes)

    # 分批查询防止 IN 列表过长
    BATCH_SIZE = 200
    price_dfs = []
    for i in range(0, len(signal_codes), BATCH_SIZE):
        batch_codes = signal_codes[i:i+BATCH_SIZE]
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
                'earliest': str(earliest_time).split(' ')[-1] if ' ' in str(earliest_time) else str(earliest_time),
                'latest': str(latest_time).split(' ')[-1] if ' ' in str(latest_time) else str(latest_time),
            })
        price_dfs.append(batch_df)

    df_prices = pd.concat(price_dfs, ignore_index=True) if price_dfs else pd.DataFrame()

    if df_prices.empty:
        return {'total_signals': len(df_signals), 'tp_count': 0, 'sl_count': 0,
                'timeout_count': len(df_signals), 'win_rate': 0}, []

    df_prices['time_td'] = pd.to_timedelta(df_prices['time'].astype(str))

    # ====== 阶段3：逐信号判定止盈止损 ======
    window_td = pd.Timedelta(minutes=window_minutes)
    trades = []

    # 按bond_code分组价格数据，避免重复切片
    price_grouped = {code: group.sort_values('time_td') for code, group in df_prices.groupby('bond_code')}

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
        bond_prices = price_grouped.get(code)
        if bond_prices is None:
            continue

        future = bond_prices[(bond_prices['time_td'] > entry_time) & (bond_prices['time_td'] <= deadline)]

        exit_type = 'timeout'
        exit_price = entry_price
        exit_time = entry_time
        max_price = entry_price
        min_price = entry_price

        if not future.empty:
            prices = future['price'].values.astype(float)
            times = future['time_td'].values
            max_price = float(np.max(prices))
            min_price = float(np.min(prices))

            # 向量化查找首次触达
            tp_hits = np.where(prices >= tp_price)[0]
            sl_hits = np.where(prices <= sl_price)[0]

            tp_idx = tp_hits[0] if len(tp_hits) > 0 else len(prices) + 1
            sl_idx = sl_hits[0] if len(sl_hits) > 0 else len(prices) + 1

            if tp_idx <= sl_idx and tp_idx < len(prices) + 1:
                # 止盈先到
                exit_type = 'tp'
                exit_price = float(prices[tp_idx])
                exit_time = times[tp_idx]
            elif sl_idx < tp_idx and sl_idx < len(prices) + 1:
                # 止损先到
                exit_type = 'sl'
                exit_price = float(prices[sl_idx])
                exit_time = times[sl_idx]
            else:
                # 都未触达 → 超时
                exit_price = float(prices[-1])
                exit_time = times[-1]

        profit_pct = round((exit_price - entry_price) / entry_price * 100, 4)
        duration_sec = int(pd.Timedelta(exit_time - entry_time).total_seconds()) if exit_time != entry_time else 0

        def _format_time(td):
            """timedelta → HH:MM:SS"""
            total_sec = int(pd.Timedelta(td).total_seconds())
            h, rem = divmod(total_sec, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        trades.append({
            'bond_code': code,
            'bond_name': sig.get('bond_name', ''),
            'signal_time': _format_time(entry_time),
            'entry_price': round(entry_price, 3),
            'exit_price': round(exit_price, 3),
            'exit_time': _format_time(exit_time),
            'exit_type': exit_type,
            'profit_pct': profit_pct,
            'duration_sec': duration_sec,
            'max_price': round(max_price, 3),
            'min_price': round(min_price, 3),
        })

    # ====== 统计汇总 ======
    if not trades:
        return {'total_signals': 0, 'tp_count': 0, 'sl_count': 0,
                'timeout_count': 0, 'win_rate': 0}, []

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
```

### 5.3 API路由（新增到 monitor.py）

```python
@monitor_bp.route('/backtest/bond/fields', methods=['GET'])
def get_backtest_bond_fields():
    """获取回测可用字段列表"""
    from gs2026.dashboard2.services.backtest_bond import BACKTEST_FIELDS
    return jsonify({'success': True, 'fields': BACKTEST_FIELDS})


@monitor_bp.route('/backtest/bond', methods=['POST'])
def run_backtest_bond():
    """执行债券量化回测"""
    from gs2026.dashboard2.services.backtest_bond import run_bond_backtest
    try:
        data = request.get_json()
        engine = _get_shared_engine()

        summary, trades = run_bond_backtest(
            engine=engine,
            date=data['date'],
            conditions=data['conditions'],
            tp_pct=float(data.get('take_profit_pct', 0.5)),
            sl_pct=float(data.get('stop_loss_pct', 0.3)),
            window_minutes=int(data.get('window_minutes', 5)),
            dedup=data.get('dedup', 'first_per_minute'),
            time_start=data.get('time_start', '09:30:00'),
            time_end=data.get('time_end', '15:00:00'),
        )

        return jsonify({'success': True, 'summary': summary, 'trades': trades})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

---

## 六、前端UI设计

### 6.1 位置

分析中心 → 买点候选条件编辑器弹窗 → 回溯配置区下方，新增「📊 量化回测」折叠区域。

### 6.2 界面布局

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 量化回测                                        [▼ 展开]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ── 日期 ──         ── 时间范围 ──                            │
│ [2026-07-08 ▼]     [09:30] ~ [15:00]                       │
│                                                             │
│ ── 入场条件 ──                                 [+ 添加条件]  │
│ ┌─────────────────────────────────────────────────────┐     │
│ │ [min1_change_pct ▼]  [> ▼]  [0.2]            [✕]   │     │
│ │ [min1_change_pct ▼]  [< ▼]  [0.8]            [✕]   │     │
│ │ [min1_amount     ▼]  [> ▼]  [10000000]       [✕]   │     │
│ └─────────────────────────────────────────────────────┘     │
│                                                             │
│ ── 去重 ──                                                  │
│ (●) 每分钟每债取首个    ( ) 不去重                            │
│                                                             │
│ ── 止盈止损 ──                                              │
│ 止盈: [0.5]%    止损: [0.3]%    窗口: [5]分钟               │
│                                                             │
│ [🚀 执行回测]  [💾 保存方案]  [📂 加载方案 ▼]                 │
├─────────────────────────────────────────────────────────────┤
│ ── 统计概览 ──                                              │
│ ┌────────┬───────┬───────┬───────┬───────┬─────────┐       │
│ │ 信号数  │止盈数 │止损数 │超时数 │ 胜率  │ 盈亏比   │       │
│ │  86    │  52  │  18  │  16  │60.5% │  2.14   │       │
│ └────────┴───────┴───────┴───────┴───────┴─────────┘       │
│                                                             │
│ ── 交易明细 ──                               [导出CSV]       │
│ ┌──────┬───────┬────────┬──────┬──────┬─────┬──────┐       │
│ │ 代码  │ 名称  │信号时间│入场价│出场价│结果 │盈亏% │       │
│ │123456│XX转债 │09:32:06│128.5│129.1 │✅止盈│+0.50│       │
│ │789012│YY转债 │09:45:12│115.2│114.8 │❌止损│-0.30│       │
│ │345678│ZZ转债 │10:12:33│102.8│102.9 │⏱超时│+0.15│       │
│ └──────┴───────┴────────┴──────┴──────┴─────┴──────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 条件构建器交互

**每行结构**：
```html
<div class="bt-condition-row">
  <select class="bt-field"><!-- 字段下拉，按group分组 --></select>
  <select class="bt-op"><!-- 操作符 --></select>
  <input class="bt-value" type="number" step="any">
  <input class="bt-value2" type="number" step="any" style="display:none"> <!-- between时显示 -->
  <button class="bt-remove" onclick="removeBtCondition(this)">✕</button>
</div>
```

**字段下拉分组**：
```html
<optgroup label="价格类">
  <option value="price">现价</option>
  <option value="open">开盘价</option>
  ...
</optgroup>
<optgroup label="涨跌类">
  <option value="change_pct">涨跌幅(%)</option>
  ...
</optgroup>
```

**操作符选择变化时**：选择 `between` 时显示第二个输入框。

### 6.4 方案管理

localStorage key: `bond_backtest_schemes_v1`

```json
[
  {
    "name": "高频放量突破",
    "conditions": [
      {"field": "min1_change_pct", "op": ">", "value": 0.2},
      {"field": "min1_change_pct", "op": "<", "value": 0.8},
      {"field": "min1_amount", "op": ">", "value": 10000000}
    ],
    "tp_pct": 0.5,
    "sl_pct": 0.3,
    "window_minutes": 5,
    "time_start": "09:30:00",
    "time_end": "15:00:00",
    "dedup": "first_per_minute"
  }
]
```

操作：保存（命名）/ 加载（下拉选择）/ 删除

### 6.5 结果导出

点击「导出CSV」，前端纯JS生成CSV文件下载：
```javascript
function exportBacktestCSV(trades) {
    const header = '代码,名称,信号时间,入场价,出场价,出场时间,结果,盈亏%,持续秒,最高价,最低价\n';
    const rows = trades.map(t =>
        `${t.bond_code},${t.bond_name},${t.signal_time},${t.entry_price},${t.exit_price},${t.exit_time},${t.exit_type},${t.profit_pct},${t.duration_sec},${t.max_price},${t.min_price}`
    ).join('\n');
    // Blob下载...
}
```

---

## 七、异常处理

| 场景 | 处理方式 |
|------|---------|
| 日期表不存在 | 后端 catch SQL异常 → 返回 "该日期无数据" |
| 条件筛选0条信号 | 返回 `total_signals: 0` + 前端提示"无命中信号，请调整条件" |
| 字段不存在（旧表无min1字段） | 后端 catch Column not found → 返回具体提示 |
| 查询超时（>15秒） | 后端 SQL timeout + 前端 loading 动画 + abort 按钮 |
| 非法字段/操作符 | 后端白名单校验，返回 400 |

---

## 八、实施步骤

| 步骤 | 内容 | 文件 | 预估工作量 |
|------|------|------|-----------|
| 1 | 新建回测引擎模块 | `dashboard2/services/backtest_bond.py` | 核心逻辑 |
| 2 | 新增API路由（2个） | `dashboard2/routes/monitor.py` | 轻量 |
| 3 | 前端：量化回测折叠面板 + CSS | `monitor.html` | UI结构 |
| 4 | 前端JS：条件构建器 + API调用 + 结果渲染 | `monitor.html` | 交互逻辑 |
| 5 | 前端JS：方案保存/加载 + CSV导出 | `monitor.html` | 辅助功能 |
| 6 | 联调验证 | - | 端到端测试 |

---

## 九、扩展性

| 需求 | 扩展方式 |
|------|---------|
| 新增sssj字段 | `BACKTEST_FIELDS` 列表追加一行 |
| 新增操作符 | `VALID_OPS` + `_build_sql_where` 增加分支 |
| 多日批量回测 | API增加 `dates: [...]`，循环调用引擎 |
| 自定义退出策略 | 引擎增加 `exit_strategy` 参数（移动止损、阶梯止盈等） |
| OR条件组合 | 条件结构增加 `logic` 字段，SQL生成器支持分组 |
| 股票sssj回测 | 复用引擎，table前缀改为 `monitor_gp_sssj_` |

---

## 十、回滚方案

实施前保存git checkpoint，如有异常回退到该commit。
