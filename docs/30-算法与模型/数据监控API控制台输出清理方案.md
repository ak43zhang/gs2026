# 数据监控API控制台输出清理方案

## 问题描述

数据监控页面调用的API在后端控制台打印了大量调试信息，影响日志可读性和性能。

## 清理原则

1. **保留错误日志**：异常和错误信息需要保留，便于排查问题
2. **清理调试日志**：正常的调试print语句需要清理或改为debug级别
3. **保留关键信息**：重要的业务日志（如命中记录保存）可以保留但改为logger
4. **使用logger替代print**：统一使用logger，便于日志级别控制

---

## 需要清理的print语句清单

### 1. 量化选债相关API (`/quant-screen`)

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 4041 | `print(f"[quant-screen] 加载方案失败: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 4063 | `print(f"[quant-screen] 保存命中记录失败: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 4072 | `print(f"[quant-screen] 计算命中序号失败: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 4185 | `print(f"[quant-screen] 保存了 {len(matches)} 条命中记录")` | ⚠️ **改为logger.info** | 业务日志，保留但改级别 |
| 4289 | `print(f"[quant-screen/hits] 计算当前价格失败: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 4311 | `print(f"[quant-screen/hits] 查询失败: {e}")` | ✅ **保留** | 错误日志，需要保留 |

### 2. 回测相关API (`/backtest`)

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 4346 | `print(f"[Backtest] Cache init failed: {e}...")` | ✅ **保留** | 错误日志，需要保留 |
| 4353 | `print(f"[Backtest] Cache hit: {cached_result['meta']['hash']}")` | ❌ **删除** | 调试日志，频繁打印 |
| 4380 | `print(f"[Backtest] Range mode: {date_start} ~ {date_end}...")` | ⚠️ **改为logger.info** | 业务日志，但改为logger |
| 4402 | `print(f"[Backtest] Single day mode: {date}...")` | ⚠️ **改为logger.info** | 业务日志，但改为logger |
| 4452 | `print(f"[Backtest] Cache write failed: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 4456 | `print(f"[Backtest] Execution time: {elapsed_seconds}s")` | ❌ **删除** | 调试日志，频繁打印 |
| 4487 | `print(f"[BacktestHistory] Error: {e}")` | ✅ **保留** | 错误日志，需要保留 |

### 3. 买点相关API

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 3846 | `print(f'[buy-points/recent] {e}')` | ✅ **保留** | 错误日志，需要保留 |
| 3869 | `print(f'[backtest/query-timepoints] {e}')` | ✅ **保留** | 错误日志，需要保留 |

### 4. 市场概览API

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 2170 | `print(f'[market-overview] _query_market_avg_fast 错误: {e}')` | ✅ **保留** | 错误日志，需要保留 |
| 2184 | `print(f'[market-overview] _query_bond_market_avg_fast 错误: {e}')` | ✅ **保留** | 错误日志，需要保留 |

### 5. 债券数据增强API

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 2778 | `logging.warning(f"[DEBUG] 调用 _get_bond_change_pct_batch...")` | ❌ **删除** | DEBUG日志，频繁打印 |
| 2784 | `logging.warning(f"[DEBUG] 涨跌幅字典大小: {len(...)}")` | ❌ **删除** | DEBUG日志，频繁打印 |
| 2836 | `logging.warning(f"[DEBUG] 代码 {code}: change_pct=...")` | ❌ **删除** | DEBUG日志，循环内打印 |

### 6. 其他监控相关

| 行号 | 当前代码 | 建议处理 | 理由 |
|------|---------|---------|------|
| 3898 | `print(f'[backtest/start] {e}')` | ✅ **保留** | 错误日志，需要保留 |
| 3932 | `print(f'[backtest/status] {e}')` | ✅ **保留** | 错误日志，需要保留 |
| 3953 | `print(f"[MONITOR] 查询异常: {e}")` | ✅ **保留** | 错误日志，需要保留 |
| 3999 | `print(f"[quant-screen] _get_current_sssj error: {e}")` | ✅ **保留** | 错误日志，需要保留 |

---

## 具体修改方案

### 方案A：保守清理（推荐）

**删除的print/logging.warning（5处）**：
- 2778行: `[DEBUG] 调用 _get_bond_change_pct_batch`
- 2784行: `[DEBUG] 涨跌幅字典大小`
- 2836行: `[DEBUG] 代码 {code}: change_pct`（循环内，最频繁）
- 4353行: `[Backtest] Cache hit`
- 4456行: `[Backtest] Execution time`

**改为logger.info（3处）**：
- 4185行: `[quant-screen] 保存了 X 条命中记录`
- 4380行: `[Backtest] Range mode`
- 4402行: `[Backtest] Single day mode`

**保留的print**：
- 所有错误/异常日志

### 方案B：激进清理

在方案A基础上，进一步删除：
- 4185行: `[quant-screen] 保存了 X 条命中记录`（改为logger.debug）
- 4380行: `[Backtest] Range mode`（删除）
- 4402行: `[Backtest] Single day mode`（删除）

---

## 实施代码示例

### 1. 删除print语句

```python
# 删除前
print(f"[Backtest] Cache hit: {cached_result['meta']['hash']}")

# 删除后（直接删除该行）
```

### 2. 改为logger.info

```python
# 修改前
print(f"[quant-screen] 保存了 {len(matches)} 条命中记录")

# 修改后
import logging
logger = logging.getLogger(__name__)
logger.info(f"[quant-screen] 保存了 {len(matches)} 条命中记录")
```

### 3. 保留错误日志（无需修改）

```python
# 保持不变
print(f"[quant-screen] 加载方案失败: {e}")
```

---

## 预期效果

| 方案 | 删除print数 | 保留print数 | 日志量减少 |
|------|-----------|------------|----------|
| 当前 | 0 | 约18个 | - |
| 方案A（保守） | 5 | 约13个 | 约30% |
| 方案B（激进） | 8 | 约10个 | 约45% |

---

## 建议

**推荐方案A（保守清理）**：
1. 保留所有错误日志，便于排查问题
2. 将业务日志改为logger.info，便于控制日志级别
3. 删除明显的调试日志（Cache hit, Execution time）

这样既能减少控制台输出，又能保留必要的日志信息。

---

## 实施检查清单

- [ ] 备份 `src/gs2026/dashboard2/routes/monitor.py`
- [ ] 按方案A实施修改
- [ ] 重启服务验证
- [ ] 检查控制台输出是否减少
- [ ] 验证功能是否正常

---

请审核方案，确认后实施。
