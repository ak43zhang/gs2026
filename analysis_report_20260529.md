# 实时买点候选 vs 回溯历史 逻辑差异分析

## 分析时间
2026-05-29 11:36

---

## 一、核心逻辑对比

| 维度 | 实时 (monitor.html) | 回溯 (backtest_worker.py) | 差异 |
|------|---------------------|---------------------------|------|
| **数据来源** | WebSocket/API 实时推送 | MySQL/Redis 历史数据 | ✅ 一致（同数据源） |
| **排行数据** | `limit=200/100` 截断展示 | `limit=0` 全量评估 | ⚠️ **重大差异** |
| **星级计算** | `level = 1 + min(bonusHit, 2)` | `level = 1 + min(bonusHit, 2)` | ✅ 一致 |
| **criticalHit** | `hasCritical && allCriticalPassed` | `has_critical && all_critical_passed` | ✅ 一致 |
| **星星颜色** | `criticalHit ? 'red' : 'yellow'` | `'red' if critical_hit else 'yellow'` | ✅ 一致 |

---

## 二、条件定义对比

### 大盘条件 (type='market')

| 条件ID | 前端 (monitor.html) | 后端 (backtest_worker.py) | 差异 |
|--------|---------------------|---------------------------|------|
| `body_gt_cur` | ✅ 有 | ✅ 有 | 一致 |
| `tick_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `strength` | ✅ 有 | ✅ 有 | 一致 |
| `bond_body_gt_cur` | ✅ 有 | ✅ 有 | 一致 |
| `bond_tick_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `stock_ud_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `stock_body_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `bond_ud_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `bond_body_ratio` | ✅ 有 | ✅ 有 | 一致 |
| `stock_phase_up` | ✅ 有 (mode='critical') | ✅ 有 | 一致 |
| `bond_phase_up` | ✅ 有 (mode='critical') | ✅ 有 | ⚠️ 后端缺 mode 字段 |

**差异1**: 后端 `_get_market_conditions()` 返回的字典中，`stock_phase_up` 和 `bond_phase_up` 没有 `mode: 'critical'` 字段，但前端有。这会导致回溯时这些条件默认不是 critical 模式。

### 个股条件 (type='stock')

| 条件ID | 前端 | 后端 | 差异 |
|--------|------|------|------|
| `net_ratio` | required | required | ✅ 一致 |
| `change_pct` | required | required | ✅ 一致 |
| `in_top_ind` | bonus | bonus | ✅ 一致 |
| `consec_attack` | required | required | ✅ 一致 |

### 联动条件 (type='link')

| 条件ID | 前端 | 后端 | 差异 |
|--------|------|------|------|
| `bond_in_rank` | bonus | bonus | ✅ 一致 |
| `bond_chg` | bonus | bonus | ✅ 一致 |
| `green_bond_in` | required | ❌ **缺失** | ⚠️ **重大差异** |
| `green_bond_out` | required | ❌ **缺失** | ⚠️ **重大差异** |

**差异2**: 后端 `_get_link_conditions()` 完全缺失绿名单条件 `green_bond_in` 和 `green_bond_out`。

---

## 三、数据字段对比

### 实时前端使用的字段
```javascript
// 排行数据字段
row.cumulative_main_net
row.max_cumulative_main_net
row.change_pct
row.consecutive_attacks
row.industry_name
row.bond_code
row.is_green_bond  // 绿名单标记

// 债券联动数据
ctx.bondMap[r.bond_code].change_pct
ctx.bondSet.has(r.bond_code)
```

### 回溯后端使用的字段
```python
# 排行数据字段（相同）
r.get('cumulative_main_net')
r.get('max_cumulative_main_net')
r.get('change_pct')
r.get('consecutive_attacks')
r.get('industry_name')
r.get('bond_code')
# ❌ 缺失: is_green_bond

# 债券联动数据（相同）
ctx['bondMap'][r.get('bond_code')].get('change_pct')
r.get('bond_code') in ctx['bondSet']
```

**差异3**: 后端没有使用 `is_green_bond` 字段，且没有绿名单条件的实现。

---

## 四、关键差异总结

| # | 差异点 | 影响 | 严重程度 |
|---|--------|------|----------|
| 1 | 后端 `stock_phase_up`/`bond_phase_up` 缺 `mode='critical'` | 回溯时这些条件默认不是 critical 模式，星星颜色逻辑可能不一致 | 中 |
| 2 | 后端缺失 `green_bond_in`/`green_bond_out` 条件 | 实时有绿名单过滤，回溯没有，候选集可能不一致 | **高** |
| 3 | 后端没有使用 `is_green_bond` 字段 | 绿名单条件无法评估 | **高** |
| 4 | 排行数据 limit 不同（前端展示截断，后端全量） | 这是设计意图，不是 bug | 无 |

---

## 五、修复建议

### 必须修复（高优先级）

1. **添加绿名单条件到后端** (`backtest_worker.py`)
   ```python
   {'id': 'green_bond_in', 'mode': 'required', 'name': '绿名单(内)',
    'fn': lambda r, p, ctx: r.get('bond_code') and r.get('bond_code') != '-' and r.get('is_green_bond') is True},
   {'id': 'green_bond_out', 'mode': 'required', 'name': '绿名单(外)',
    'fn': lambda r, p, ctx: r.get('bond_code') and r.get('bond_code') != '-' and r.get('is_green_bond') is not True},
   ```

2. **添加 `is_green_bond` 字段到 enrichment** (如果还没添加)
   - 检查 `_enrich_stock_data` 是否设置了 `is_green_bond`

### 建议修复（中优先级）

3. **添加 `mode='critical'` 到阶段条件**
   ```python
   {'id': 'stock_phase_up', 'name': '股票阶段(升/弹)', 'mode': 'critical', ...}
   {'id': 'bond_phase_up', 'name': '债券阶段(升/弹)', 'mode': 'critical', ...}
   ```

---

## 六、验证方法

1. 对比同一天同一时间的实时候选和回溯候选
2. 检查绿名单条件开启时，两者候选集是否一致
3. 检查阶段条件设为 critical 时，星星颜色是否一致

