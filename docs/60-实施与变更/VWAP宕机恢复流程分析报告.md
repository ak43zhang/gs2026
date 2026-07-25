# VWAP 宕机恢复流程分析报告

**文档版本**: v1.0  
**生成时间**: 2026-07-26 03:37  
**分析对象**: `monitor_bond.py` 中 VWAP 相关变量的宕机恢复机制  
**状态**: 🔴 发现问题 - VWAP累积变量无恢复逻辑

---

## 一、核心结论（重要）

**`_mkt_trend_vwap_sum_pv` 和 `_mkt_trend_vwap_sum_v` 这两个VWAP累积变量确实没有宕机恢复逻辑！**

这是一个**设计缺陷/遗漏**，导致服务重启后VWAP从0开始重新累积，而非从宕机前的状态恢复。

---

## 二、VWAP 相关变量清单

| 变量名 | 类型 | 用途 | 是否有恢复逻辑 |
|--------|------|------|----------------|
| `_mkt_trend_vwap_sum_pv` | float | Σ(涨跌幅 × 成交额) 累积值 | ❌ **无** |
| `_mkt_trend_vwap_sum_v` | float | Σ(成交额) 累积值 | ❌ **无** |
| `_mkt_trend_day_high` | float | 日内最高点 | ❌ **无** |
| `_mkt_trend_day_low` | float | 日内最低点 | ❌ **无** |
| `_mkt_trend_last_new_low_time` | int/None | 上次创新低时间(秒) | ❌ **无** |
| `_mkt_trend_slope_10m_cache` | deque | 10分钟斜率缓存 | ❌ **无** |
| `_peak_vol_state` | dict | 放量高点状态 | ✅ **有** |
| `_high_state` | dict | 日内高点状态 | ✅ **有** |

---

## 三、对比分析：为什么 _peak_vol_state 有恢复，VWAP没有？

### 3.1 _peak_vol_state 的恢复逻辑（第480-511行）

```python
def _recover_indicators(engine, date):
    """ONE-TIME启动恢复peak_vol和high_distance"""
    global _peak_vol_state, _high_state, _indicator_recovered
    if _indicator_recovered:
        return
    try:
        from sqlalchemy import text as sa_text
        table = f"monitor_zq_sssj_{date}"
        sql = sa_text(f"""
            SELECT bond_code, MAX(amount) as max_amt, MAX(change_pct) as max_cpct
            FROM {table}
            GROUP BY bond_code
        """)
        # ... 从MySQL查询历史数据恢复状态
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
            for r in rows:
                code, max_amt, max_cpct = r[0], float(r[1]), float(r[2])
                _peak_vol_state[code] = {'max_amount': max_amt, 'price_at_max': 0}
                _high_state[code] = {'max_cpct': max_cpct}
        _indicator_recovered = True
        logger.info(f"[indicators] 恢复成功: {len(rows)} 只债券")
    except Exception as e:
        logger.warning(f"[indicators] 恢复失败(降级运行): {e}")
        _indicator_recovered = True
```

**特点**：
- 从MySQL `monitor_zq_sssj_{date}` 表查询历史数据
- 恢复 `_peak_vol_state` 和 `_high_state`
- **完全不涉及 `_mkt_trend_*` 变量**

### 3.2 VWAP 变量的现状

```python
# 初始化（第707-708行）
_mkt_trend_vwap_sum_pv = 0.0    # 仅初始化，无恢复
_mkt_trend_vwap_sum_v = 0.0     # 仅初始化，无恢复

# 日期切换重置（第1051-1052行）
if _mkt_trend_date != current_date:
    _mkt_trend_vwap_sum_pv = 0.0  # 直接置0
    _mkt_trend_vwap_sum_v = 0.0   # 直接置0
    ...

# 没有类似 _recover_mkt_trend 的函数！
```

---

## 四、数据流分析：VWAP 指标如何存储

### 4.1 存储链路

```
compute_mkt_trend_indicators()
  ↓ 返回 dict: {'mkt_vwap_bias': ..., 'mkt_vwap': ..., ...}
  ↓
compute_ext_indicators()
  ↓ combined = {**ext, **mkt_ext, **mkt_trend}
  ↓ ext_indicators_list.append(json.dumps(combined))
  ↓ df_now['ext_indicators'] = JSON字符串
  ↓
msac.save_dataframe_async(df_now, table, time_full, expire)
  ↓ 异步写入
MySQL: monitor_zq_sssj_{date} 表 (ext_indicators 字段存JSON)
Redis: {table}:{time_full} (同样包含 ext_indicators)
```

### 4.2 关键问题

**存储的是 `mkt_vwap_bias`（结果值），而非 `_mkt_trend_vwap_sum_pv/v`（累积值）！**

| 存储内容 | 是否可恢复VWAP | 说明 |
|----------|--------------|------|
| `mkt_vwap_bias` | ❌ 不可 | 这是结果，不是累积状态 |
| `_mkt_trend_vwap_sum_pv` | ❌ 未存储 | 需要此值才能恢复 |
| `_mkt_trend_vwap_sum_v` | ❌ 未存储 | 需要此值才能恢复 |

**数学关系**：
```
mkt_vwap = _mkt_trend_vwap_sum_pv / _mkt_trend_vwap_sum_v
mkt_vwap_bias = mkt_vs_open_pct - mkt_vwap
```

**仅从 `mkt_vwap_bias` 无法反推出累积值**，因为缺少分母 `_mkt_trend_vwap_sum_v`。

---

## 五、宕机恢复的正确做法

### 5.1 方案A：存储并恢复累积值（推荐）

**步骤1**：新增 Redis 存储（每tick或每30秒）
```python
# 在 compute_mkt_trend_indicators 末尾
redis_client.hset(f"mkt_trend:{current_date}", 
    "vwap_sum_pv", _mkt_trend_vwap_sum_pv)
redis_client.hset(f"mkt_trend:{current_date}", 
    "vwap_sum_v", _mkt_trend_vwap_sum_v)
redis_client.hset(f"mkt_trend:{current_date}", 
    "day_high", _mkt_trend_day_high)
redis_client.hset(f"mkt_trend:{current_date}", 
    "day_low", _mkt_trend_day_low)
```

**步骤2**：新增恢复函数
```python
def _recover_mkt_trend(date):
    """恢复大盘趋势指标状态"""
    global _mkt_trend_vwap_sum_pv, _mkt_trend_vwap_sum_v
    global _mkt_trend_day_high, _mkt_trend_day_low
    try:
        r = redis_util._get_redis_client()
        _mkt_trend_vwap_sum_pv = float(r.hget(f"mkt_trend:{date}", "vwap_sum_pv") or 0)
        _mkt_trend_vwap_sum_v = float(r.hget(f"mkt_trend:{date}", "vwap_sum_v") or 0)
        _mkt_trend_day_high = float(r.hget(f"mkt_trend:{date}", "day_high") or -999)
        _mkt_trend_day_low = float(r.hget(f"mkt_trend:{date}", "day_low") or 999)
        logger.info(f"[mkt_trend] 恢复成功: PV={_mkt_trend_vwap_sum_pv:.2f}, V={_mkt_trend_vwap_sum_v:.2f}")
    except Exception as e:
        logger.warning(f"[mkt_trend] 恢复失败(从0开始): {e}")
```

**步骤3**：在日期切换时调用恢复
```python
if _mkt_trend_date != current_date:
    _recover_mkt_trend(current_date)  # 新增
    if _mkt_trend_date is None:  # 首次启动或跨天
        # 保持恢复的值或初始化
        pass
```

### 5.2 方案B：从MySQL历史数据反算（备选）

如果Redis未存储，可以从MySQL的 `ext_indicators` 字段反算近似值：

```python
def _recover_mkt_trend_from_mysql(engine, date, current_time):
    """从MySQL历史tick反算VWAP累积值（近似）"""
    # 查询当日所有历史tick的 amount 和 change_pct
    # 重新计算累积值
    # 缺点：IO开销大，只能近似
```

**缺点**：
- 需要扫描当日所有历史数据，IO开销大
- 只能得到近似值（因为 `mkt_vs_open_pct` 是所有债券均值，非单个）

---

## 六、影响评估

| 场景 | 影响 | 严重程度 |
|------|------|----------|
| 服务重启（盘中） | VWAP从0开始，早盘数据失真，Bias计算错误 | 🔴 **高** |
| 每日首次启动 | 无影响（本来就从0开始） | 🟢 低 |
| 跨天运行 | 自动重置，无影响 | 🟢 低 |
| 回测 | 无影响（回测用历史数据重新计算） | 🟢 低 |

**主要风险**：
- 盘中重启后，VWAP需要重新累积，**前10-30分钟数据不可靠**
- 如果此时有基于 `mkt_vwap_bias` 的交易信号，可能产生误判

---

## 七、修复建议

### 优先级：🔴 高（建议尽快修复）

**原因**：
- 盘中服务重启是常见运维操作
- VWAP是重要的趋势环境指标，影响信号质量
- 修复成本低（新增Redis存储+恢复函数，约30行代码）

### 实施步骤

1. **新增存储**：在 `compute_mkt_trend_indicators` 每30秒存储累积值到Redis
2. **新增恢复函数**：`_recover_mkt_trend(date)`
3. **修改日期切换逻辑**：调用恢复函数
4. **测试验证**：模拟重启，验证恢复值正确

---

## 八、相关代码位置

| 功能 | 文件 | 行号 |
|------|------|------|
| VWAP计算 | monitor_bond.py | 1069-1074 |
| 日期切换重置 | monitor_bond.py | 1050-1057 |
| 有恢复的指标 | monitor_bond.py | 480-511 |
| ext_indicators合并 | monitor_bond.py | 1199-1204 |
| DataFrame存储 | monitor_stock.py | save_dataframe_async |

---

## 九、结论

**问题确认**：`_mkt_trend_vwap_sum_pv` 和 `_mkt_trend_vwap_sum_v` 确实没有宕机恢复逻辑，这是一个设计遗漏。

**原因**：
- 开发者只考虑了 `_peak_vol_state` 等个券级状态的恢复
- 大盘级累积变量（VWAP、日内高低点）被遗漏
- 存储的是结果值（`mkt_vwap_bias`）而非累积值，无法反推

**建议**：实施上述方案A，新增Redis存储和恢复逻辑。

