# 量化回测执行速度优化方案：SQL条件下推与多日并行

## 1. 背景

### 1.1 当前架构

```
Phase 1（信号检测）：加载全表60万+行 → JSON展开 → pandas条件评估 → 得到信号（几百条）
Phase 2（价格序列）：查信号债的价格序列（信号时间+窗口）→ 用于TP/SL计算
Phase 3（止盈止损）：逐信号逐tick判定止盈/止损/超时
```

### 1.2 性能瓶颈

| 阶段 | 操作 | 耗时 | 问题 |
|------|------|------|------|
| Phase 1 | 加载全表60万+行 | 3-8秒 | 不做SQL过滤，全量加载到pandas |
| Phase 1.5 | `expand_ext_indicators` JSON展开 | 1-3秒 | 60万行逐行JSON解析 |
| Phase 1.5 | `evaluate_conditions` pandas评估 | 0.5-1秒 | DataFrame过滤 |
| Phase 2 | 查询价格序列 | 1-3秒 | 必要操作，已较高效 |
| Phase 3 | 逐信号TP/SL判定 | 0.1-0.5秒 | 已用numpy向量化 |
| 多日 | 30天串行执行 | 30×上述 | 无并行 |

**单日总耗时**：6-15秒
**30天总耗时**：3-7分钟

---

## 2. 两阶段设计分析

### 2.1 Phase 1 的职责

**找信号**：哪些 (bond_code, time) 满足入场条件

- 需要**多列**（19+列）来评估复杂条件
- 只关心**信号时间范围**（time_start ~ time_end）
- 输出：几百条信号行

### 2.2 Phase 2 的职责

**取价格序列**：信号之后的走势，用于TP/SL判定

- 只需**3列**（bond_code, time, price）
- 时间需**延伸到信号时间+窗口**（可能超出Phase 1的time_end）
- 只查**信号债**（不是全部200+债）

### 2.3 Phase 2 存在的必要性

```
Phase 1 时间范围：time_start ~ time_end（如 09:30 ~ 14:50）
Phase 2 时间范围：earliest_signal ~ latest_signal + window_minutes

如果14:50有信号，window=10min → 需要数据到15:00
Phase 1 没加载这部分数据 → Phase 2 必须存在
```

**结论**：Phase 2 不是冗余设计，它获取的是信号之后的价格轨迹，这些数据不满足入场条件，Phase 1（SQL下推后）不会返回它们。

---

## 3. 优化方案

### 3.1 优化1：Phase 1 条件全下推SQL（P0，最大提升）

#### 核心思路

让MySQL在C层面做条件过滤，不再加载60万行到Python。

#### 当前流程

```python
# 加载全表
load_sql = "SELECT * FROM table WHERE time >= :start AND time <= :end"
df_all = pd.read_sql(load_sql, ...)  # 60万行
df_all = expand_ext_indicators(df_all)  # 60万行JSON解析
mask = evaluate_conditions(df_all, ...)  # pandas评估
df_signals = df_all[mask]  # 得到几百条
```

#### 优化后流程

```python
# SQL直接过滤，只返回信号行
where_clause, params = _build_full_where(conditions, groups)
signal_sql = f"""
    SELECT bond_code, bond_name, time, price, change_pct, amount
    FROM {table}
    WHERE time >= :time_start AND time <= :time_end
    AND ({where_clause})
"""
df_signals = pd.read_sql(signal_sql, ...)  # 直接得到几百条
```

#### 条件类型处理

| 条件类型 | SQL表达式 | 示例 |
|----------|----------|------|
| 普通字段 | `field op value` | `change_pct > 0.2` |
| JSON字段 | `CAST(JSON_EXTRACT(ext_indicators, '$.field') AS DOUBLE) op value` | `JSON_EXTRACT(..., '$.weighted_slope_2m') > 0.001` |
| 字段间比较 | `field1 op field2` | `change_pct > mkt_change_1m_pct` |
| between | `field BETWEEN lo AND hi` | `amount BETWEEN 1000 AND 5000` |

#### 新增函数：`_build_full_where`

```python
def _build_full_where(conditions, groups):
    """
    构建完整WHERE子句（基础条件AND + 条件组OR/AND）
    
    Args:
        conditions: 基础条件列表（AND关系）
        groups: 条件组列表
            - mode='and': 组内条件AND
            - mode='or': 子组间OR，子组内AND
    
    Returns:
        (where_clause_str, params_dict)
    """
    parts = []
    params = {}
    
    # 1. 基础条件（AND）
    if conditions:
        base_clause, base_params = _build_sql_where(conditions, 'base')
        if base_clause:
            parts.append(f"({base_clause})")
            params.update(base_params)
    
    # 2. 条件组
    for gi, g in enumerate(groups):
        if g.get('mode') == 'or' and g.get('subgroups'):
            # OR组：子组间OR，子组内AND
            or_parts = []
            for sgi, sg in enumerate(g['subgroups']):
                sg_conds = sg.get('conditions', [])
                if not sg_conds:
                    continue
                sg_clause, sg_params = _build_sql_where(sg_conds, f'g{gi}_s{sgi}')
                if sg_clause:
                    or_parts.append(f"({sg_clause})")
                    params.update(sg_params)
            if or_parts:
                parts.append(f"({' OR '.join(or_parts)})")
        else:
            # AND组
            g_conds = g.get('conditions', [])
            if not g_conds:
                continue
            g_clause, g_params = _build_sql_where(g_conds, f'g{gi}')
            if g_clause:
                parts.append(f"({g_clause})")
                params.update(g_params)
    
    final_clause = ' AND '.join(parts) if parts else '1=1'
    return final_clause, params
```

#### 收益

- Phase 1 从加载60万行 → 只返回几百条信号
- 省去 `expand_ext_indicators`（60万行JSON解析）
- 省去 `evaluate_conditions`（pandas评估）
- **单日提速 5-10x**

---

### 3.2 优化2：多日并行执行（P1）

#### 核心思路

每天的回测相互独立，使用ThreadPoolExecutor并行执行。

#### 实现

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_bond_backtest_range(engine, dates, conditions, ...):
    max_workers = min(4, len(dates))  # 最多4线程
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for date in dates:
            f = executor.submit(
                run_bond_backtest, engine, date, 
                conditions, tp_pct, sl_pct, window_minutes, ...
            )
            futures[f] = date
        
        for f in as_completed(futures):
            date = futures[f]
            try:
                summary, trades = f.result()
                results.append({'date': date, 'summary': summary, 'trades': trades})
            except Exception as e:
                results.append({'date': date, 'error': str(e)})
    
    # 按日期排序
    results.sort(key=lambda x: x['date'])
    return results
```

#### 注意事项

- SQLAlchemy engine 是线程安全的（内部有连接池）
- 需要确保每个线程使用独立的connection
- max_workers=4 避免数据库连接池耗尽

#### 收益

- 30天回测从串行 → 4线程并行
- **多日提速 3-4x**

---

## 4. 不做的优化（及原因）

| 优化项 | 不做原因 |
|--------|----------|
| 日级DataFrame缓存 | 用户明确不需要 |
| 消除Phase 2 | Phase 2 是必要的（获取信号后的价格轨迹） |
| 延迟JSON展开 | Phase 1 全SQL化后不再需要Python侧JSON展开 |
| 预计算JSON列为物理列 | 改动大，收益被SQL下推覆盖 |

---

## 5. 预期效果

| 场景 | 优化前 | 优化后 | 提升倍数 |
|------|--------|--------|----------|
| 单日回测 | 6-15秒 | 1-3秒 | **5-10x** |
| 30天回测 | 3-7分钟 | 30-60秒 | **5-8x** |

---

## 6. 实施步骤

| 步骤 | 内容 | 改动文件 |
|------|------|----------|
| 1 | 新增 `_build_full_where()` 函数 | `backtest_bond.py` |
| 2 | 重写 `run_bond_backtest()` Phase 1 逻辑 | `backtest_bond.py` |
| 3 | 移除 Phase 1 的 `expand_ext_indicators` + `evaluate_conditions` | `backtest_bond.py` |
| 4 | 改写 `run_bond_backtest_range()` 为并行版 | `backtest_bond.py` |
| 5 | 验证：对比优化前后结果一致性 | 手动测试 |

---

## 7. 风险评估

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| SQL条件构建有误导致信号遗漏 | 中 | 对比优化前后结果，确保一致 |
| JSON_EXTRACT性能不如预期 | 低 | MySQL 8.0 对JSON有优化，仍比Python快 |
| 多线程连接池耗尽 | 低 | 限制max_workers=4，使用pool_size>=5 |
| 条件组OR逻辑SQL构建复杂 | 低 | 复用现有 `_build_sql_where`，已覆盖所有操作符 |

---

## 8. 验证方案

优化后需验证结果一致性：

```python
# 对比测试
old_summary, old_trades = run_bond_backtest_old(engine, '20260720', ...)
new_summary, new_trades = run_bond_backtest_new(engine, '20260720', ...)

assert old_summary['total_signals'] == new_summary['total_signals']
assert len(old_trades) == len(new_trades)
for ot, nt in zip(old_trades, new_trades):
    assert ot['bond_code'] == nt['bond_code']
    assert ot['signal_time'] == nt['signal_time']
    assert abs(ot['profit_pct'] - nt['profit_pct']) < 0.0001
```

---

## 9. 实施记录（2026-07-21）

### 9.1 第一次实施：纯SQL下推（已回退）

**问题**：将所有条件（含JSON字段）全部下推到SQL，导致MySQL使用 `JSON_EXTRACT` 做全表扫描，性能反而退化（单日从5s→30s+）。

**根因**：`CAST(JSON_EXTRACT(ext_indicators, '$.field') AS DOUBLE)` 无索引，MySQL逐行解析JSON比pandas向量化慢5-10x。

### 9.2 第二次实施：混合策略（最终方案）

**核心改动**：

1. **条件分离**：
   - 物理列条件（`_PHYSICAL_COLUMNS`中的字段）→ SQL WHERE 下推
   - JSON字段条件 / 字段间比较 / 条件组(groups) → pandas 评估

2. **`_PHYSICAL_COLUMNS` 定义**（新增）：
```python
_PHYSICAL_COLUMNS = {
    'bond_code', 'bond_name', 'time', 'price', 'change_pct', 'amount',
    'amount_rank', 'min1_change_pct', 'min1_amount', 'min1_amount_rank',
    'slope_short', 'slope_long', 'peak_vol_bias', 'high_distance',
    'mkt_slope_short', 'mkt_slope_long', 'mkt_peak_vol_bias', 'mkt_high_distance'
}
```

3. **Phase 1 混合流程**：
```python
# 分离条件
sql_conditions = [物理列条件]
pandas_conditions = [JSON条件 + 字段比较]

# SQL预过滤（仅物理列，使用索引）
SELECT ... FROM table WHERE time范围 AND {sql_conditions}
→ 从60万行降到5万~10万行

# 如果有pandas条件，在预过滤数据上评估
if has_pandas_eval:
    expand_ext_indicators(df)  # 仅对5万行做JSON展开
    evaluate_conditions(df, pandas_config)
```

4. **Phase 2 batch扩大**：200 → 2000（减少数据库轮次）

5. **并行线程**：4 → 8

6. **进度打印**：每天完成时输出 `[Backtest] 进度 N/M 完成: date`

### 9.3 其他同日修改

- 新增 `_build_full_where()` 函数：支持基础条件AND + 条件组OR/AND的SQL构建
- 新增 `_calc_max_drawdown()` 函数：O(n)算法计算最大回撤
- summary新增 `max_drawdown_pct` 字段
- 多日汇总(`run_bond_backtest_range`)修复跨日最大回撤计算
- 新增执行时间(`elapsed_seconds`)返回

---

*更新时间：2026-07-21*
*版本：v1.1*
