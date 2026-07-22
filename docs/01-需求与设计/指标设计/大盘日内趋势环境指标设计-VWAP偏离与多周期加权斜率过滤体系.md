# 大盘日内趋势环境指标设计 - VWAP偏离与多周期加权斜率过滤体系

> 创建时间：2026-07-22  
> 状态：设计完成，待实施  
> 依赖文档：《债券监控-斜率指标体系与滞后性解决方案》  
> 核心目标：通过宽表字段+入场条件配置，过滤单边下行行情，允许反转后交易

---

## 一、问题背景

### 1.1 痛点

- **策略**：斜率共振v3，使用 `mkt_weighted_slope_2m`（EWLR half_life=30s）作为大盘方向信号
- **缺陷**：2分钟加权斜率只反映局部反弹动量，无法识别"全局重心下移"
- **后果**：单边下行行情中（如2026-07-13），每次短暂反弹都满足入场条件，不断抄下跌中继，连续亏损

### 1.2 目标

| 需求 | 说明 |
|------|------|
| 杜绝单边下行 | 日内持续下跌时，禁止做多 |
| 允许反转交易 | 下跌停止+方向翻转后，可以入场 |
| 介入不滞后 | 反转确认后尽快入场，不错失行情 |
| 条件化配置 | 所有指标作为宽表字段，用户自定义入场条件组合 |

### 1.3 设计原则

1. **全部作为宽表字段**，通过入场条件自定义过滤（不设独立"环境开关"）
2. **每tick更新**，与现有指标同频（3秒/tick）
3. **使用EWLR体系**（不用OLS固定窗口），保持低滞后
4. **VWAP基于大盘涨跌幅计算**（即所有可转债均价的变化率）
5. **不预设方案**，用户通过条件自由组合

---

## 二、新增指标定义

### 2.1 指标总览

| 指标名 | 中文名 | 算法 | 滞后 | 存储 |
|--------|--------|------|------|------|
| `mkt_vs_open_pct` | 大盘涨跌幅 | `mean(所有债券change_pct)` | 零 | ext_indicators |
| `mkt_vwap_bias` | 大盘VWAP偏离 | `当前涨跌幅 - VWAP(涨跌幅)` | 零 | ext_indicators |
| `mkt_weighted_slope_5m` | 大盘加权斜率(5min) | EWLR, half_life=75s | ~25s | ext_indicators |
| `mkt_weighted_slope_10m` | 大盘加权斜率(10min) | EWLR, half_life=150s | ~50s | ext_indicators |
| `mkt_day_position` | 日内位置% | `(当前-日低)/(日高-日低)*100` | 零 | ext_indicators |
| `mkt_new_low_distance` | 距新低分钟数 | `(当前时间 - 最后创新低时间) / 60` | 零 | ext_indicators |

### 2.2 与现有指标的关系

```
现有指标（已实现）：
├── mkt_weighted_slope_2m    EWLR half_life=30s   延迟10-15s  （局部动量）
├── mkt_change_1m_pct        1分钟差分            延迟0s      （瞬时动量）
└── mkt_price_acceleration   斜率差分             延迟10-15s  （拐点检测）

新增指标（本方案）：
├── mkt_vs_open_pct          均值计算             延迟0s      （日内方向）
├── mkt_vwap_bias            累计量价均价偏离      延迟0s      （趋势强度）
├── mkt_weighted_slope_5m    EWLR half_life=75s   延迟~25s    （中周期趋势）
├── mkt_weighted_slope_10m   EWLR half_life=150s  延迟~50s    （长周期趋势）
├── mkt_day_position         高低点比例            延迟0s      （相对位置）
└── mkt_new_low_distance     时间距离             延迟0s      （结构判断）
```

---

## 三、各指标详细计算逻辑

### 3.1 `mkt_vs_open_pct`（大盘涨跌幅）

```python
# 每tick计算：所有可转债涨跌幅的均值
mkt_vs_open_pct = round(float(df_now['change_pct'].mean()), 4)
```

**特性**：
- 零滞后，实时反映大盘相对开盘的位置
- 正值=大盘上涨，负值=大盘下跌
- 单边下行日全天持续为负且加深

**条件示例**：`mkt_vs_open_pct > -0.3`（大盘跌幅不超0.3%才允许交易）

---

### 3.2 `mkt_vwap_bias`（大盘VWAP偏离）

```python
# 全局变量（每日重置）
_mkt_vwap_sum_pv = 0.0   # Σ(mkt_pct × total_amount)
_mkt_vwap_sum_v = 0.0    # Σ(total_amount)

# 每tick累计
total_amount = float(df_now['amount'].sum())  # 当前tick全市场总成交额
mkt_pct = float(df_now['change_pct'].mean())  # 当前大盘涨跌幅

_mkt_vwap_sum_pv += mkt_pct * total_amount
_mkt_vwap_sum_v += total_amount

# VWAP = 成交额加权的大盘涨跌幅均值（从开盘到当前）
mkt_vwap = _mkt_vwap_sum_pv / _mkt_vwap_sum_v if _mkt_vwap_sum_v > 0 else 0.0

# 偏离 = 当前值 - VWAP
mkt_vwap_bias = round(mkt_pct - mkt_vwap, 4)
```

**特性**：
- 零滞后，实时反映价格与量价均线的关系
- 正值=价格在VWAP上方（多头环境），负值=在VWAP下方（空头环境）
- 单边下行日：价格全天在VWAP下方，反弹触碰VWAP即回落
- VWAP权重使用成交额（`sum(amount)`），反映资金流向

**核心价值**：
- 区分"下跌中继反弹"（反弹到VWAP即回落，bias始终为负）
- 与"真实反转"（突破VWAP并站稳，bias转正）

**条件示例**：`mkt_vwap_bias > 0`（价格在均价线上方才允许交易）

---

### 3.3 `mkt_weighted_slope_5m`（大盘加权斜率5分钟）

```python
# 全局变量
_mkt_slope_5m_cache = []  # [(seconds, mkt_pct), ...]

# 每tick更新
_mkt_slope_5m_cache.append((current_seconds, mkt_pct))
cutoff = current_seconds - 375  # 5 × half_life = 5 × 75s
_mkt_slope_5m_cache = [(ts, p) for ts, p in _mkt_slope_5m_cache if ts >= cutoff]

# EWLR计算（与现有_calc_weighted_slope完全相同，仅half_life不同）
mkt_weighted_slope_5m = round(_calc_weighted_slope(
    prices=[p for _, p in _mkt_slope_5m_cache],
    times=[t for t, _ in _mkt_slope_5m_cache],
    half_life=75  # 区别：2min用30s，5min用75s
), 6)
```

**特性**：
- 延迟~25-30秒（8-10个tick确认方向翻转）
- 与 `mkt_weighted_slope_2m` (half_life=30s) 形成2.5倍层次关系
- 能过滤持续1-3分钟的"假反弹"（2min斜率会被骗，5min不会）
- 真实反转（持续>3分钟）可在25秒内确认

**条件示例**：`mkt_weighted_slope_5m > 0`（中周期趋势向上）

---

### 3.4 `mkt_weighted_slope_10m`（大盘加权斜率10分钟）

```python
# 全局变量
_mkt_slope_10m_cache = []  # [(seconds, mkt_pct), ...]

# 每tick更新
_mkt_slope_10m_cache.append((current_seconds, mkt_pct))
cutoff = current_seconds - 750  # 5 × half_life = 5 × 150s
_mkt_slope_10m_cache = [(ts, p) for ts, p in _mkt_slope_10m_cache if ts >= cutoff]

# EWLR计算
mkt_weighted_slope_10m = round(_calc_weighted_slope(
    prices=[p for _, p in _mkt_slope_10m_cache],
    times=[t for t, _ in _mkt_slope_10m_cache],
    half_life=150
), 6)
```

**特性**：
- 延迟~50-60秒（15-20个tick确认方向翻转）
- 单边下行日开盘后5-10分钟转负，持续整天为负
- 不会被5分钟以内的反弹干扰
- 适合作为"大方向"硬过滤器

**条件示例**：`mkt_weighted_slope_10m > -0.001`（大趋势没有强烈下行）

---

### 3.5 `mkt_day_position`（日内位置百分比）

```python
# 全局变量（每日重置）
_mkt_day_high = -999.0
_mkt_day_low = 999.0

# 每tick更新
mkt_pct = float(df_now['change_pct'].mean())
_mkt_day_high = max(_mkt_day_high, mkt_pct)
_mkt_day_low = min(_mkt_day_low, mkt_pct)

# 计算位置
if _mkt_day_high > _mkt_day_low:
    mkt_day_position = round((mkt_pct - _mkt_day_low) / (_mkt_day_high - _mkt_day_low) * 100, 1)
else:
    mkt_day_position = 50.0  # 高低点相同，中性
```

**特性**：
- 零滞后
- 0% = 处于日内最低点，100% = 处于日内最高点
- 单边下行时始终接近0-20%（贴着底部运行）
- 反弹后会快速升高

**条件示例**：`mkt_day_position > 30`（不在日内最底部区域）

---

### 3.6 `mkt_new_low_distance`（距上次创新低的分钟数）

```python
# 全局变量（每日重置）
_mkt_last_new_low_time = None  # 最后一次创新低的时间（秒）
_mkt_day_low_val = 999.0

# 每tick更新
mkt_pct = float(df_now['change_pct'].mean())

if mkt_pct <= _mkt_day_low_val:
    _mkt_day_low_val = mkt_pct
    _mkt_last_new_low_time = current_seconds

# 计算距离（分钟，float保留1位小数）
if _mkt_last_new_low_time is not None:
    mkt_new_low_distance = round((current_seconds - _mkt_last_new_low_time) / 60.0, 1)
else:
    mkt_new_low_distance = 999.0  # 从未创过新低（开盘第一个tick）
```

**特性**：
- 零滞后
- 单边下行时：不断创新低，此值持续接近0
- 停止创新低后：此值随时间线性增长
- 反转确认的核心结构指标："不再创新低"是趋势反转的第一信号

**条件示例**：`mkt_new_low_distance > 5`（至少5分钟没有创新低）

---

## 四、滞后性分析

### 4.1 各指标延迟对比

| 指标 | 算法 | 延迟 | 单边下行识别 | 反转识别 |
|------|------|------|-------------|---------|
| `mkt_vs_open_pct` | 均值 | 0s | 即时（值为负） | 即时（值回正） |
| `mkt_vwap_bias` | 累计均价 | 0s | 即时（持续为负） | 即时（突破转正） |
| `mkt_weighted_slope_2m` | EWLR 30s | 10-15s | 被假反弹欺骗 | 10s |
| `mkt_weighted_slope_5m` | EWLR 75s | 25-30s | 稳定为负 | 25s |
| `mkt_weighted_slope_10m` | EWLR 150s | 50-60s | 稳定为负 | 50s |
| `mkt_day_position` | 高低比 | 0s | 即时（接近0） | 即时（快速升高） |
| `mkt_new_low_distance` | 时间记录 | 0s | 即时（接近0） | 即时（开始增长） |
| OLS 30分钟（不采用） | 固定窗口 | 10-15min | — | **不可接受** |

### 4.2 多周期EWLR参数设计依据

| 周期 | half_life | 缓存窗口 | 有效样本数 | 延迟 | 倍数关系 |
|------|-----------|---------|-----------|------|---------|
| 2min（已有） | 30s | 150s | ~50 ticks | 10-15s | 基准 |
| 5min（新增） | 75s | 375s | ~125 ticks | 25-30s | 2.5× |
| 10min（新增） | 150s | 750s | ~250 ticks | 50-60s | 5× |

**2.5倍递进关系**确保各周期信号有明确区分度，不会同步误判。

---

## 五、行情场景验证

### 5.1 场景A：单边下行（2026-07-13）

```
特征：开盘后持续下跌，全天低点不断刷新

指标表现：
├── mkt_vs_open_pct:         开盘后快速转负，持续加深 (-0.5% → -1.2%)
├── mkt_vwap_bias:           全天为负（价格始终在VWAP下方）
├── mkt_weighted_slope_5m:   开盘5分钟后转负，持续为负
├── mkt_weighted_slope_10m:  开盘10分钟后转负，持续为负
├── mkt_day_position:        持续接近0-20%（贴着底部）
└── mkt_new_low_distance:    持续小值（<2分钟），不断创新低

过滤效果：任何一个条件都能有效拦截
```

### 5.2 场景B：V型反转（早盘暴跌，午后反转）

```
特征：上午持续下跌，午后停止创新低并反弹

指标表现时间线：
10:00（下跌中）：
├── mkt_vwap_bias: -0.3（远低于VWAP）→ 禁止
├── mkt_weighted_slope_10m: -0.002 → 禁止
├── mkt_new_low_distance: 0.5分钟 → 禁止

13:10（停止创新低5分钟）：
├── mkt_new_low_distance: 5.0 → 通过 ✓
├── mkt_weighted_slope_5m: 转正 → 通过 ✓（~25s延迟）
├── mkt_vwap_bias: -0.05（接近VWAP）→ 可放宽条件

13:15（站稳VWAP上方）：
├── mkt_vwap_bias: +0.02 → 通过 ✓
├── mkt_weighted_slope_10m: 开始收敛 → 可放宽条件

结论：反转后约3-5分钟可确认入场（5min斜率25s + 站稳VWAP确认）
```

### 5.3 场景C：正常上涨日

```
特征：开盘后温和上涨

指标表现：
├── mkt_vs_open_pct:         持续为正
├── mkt_vwap_bias:           大部分时间为正
├── mkt_weighted_slope_5m:   持续为正
├── mkt_weighted_slope_10m:  持续为正
├── mkt_day_position:        50-100%区间
└── mkt_new_low_distance:    持续增大（开盘后几乎不创新低）

过滤效果：所有条件都满足，不影响正常交易
```

### 5.4 场景D：震荡市（围绕VWAP来回穿插）

```
特征：无明确方向，价格在VWAP附近震荡

指标表现：
├── mkt_vwap_bias:           在-0.05 ~ +0.05之间波动
├── mkt_weighted_slope_5m:   在-0.0005 ~ +0.0005之间波动
├── mkt_weighted_slope_10m:  接近0
├── mkt_day_position:        30-70%区间

过滤效果：
- 严格条件（vwap_bias > 0 AND slope_10m > 0）→ 约50%时间允许交易
- 宽松条件（vwap_bias > -0.1）→ 大部分时间允许交易
- 用户可根据回测结果自行调整阈值
```

---

## 六、条件组合使用指南

### 6.1 保守型（杜绝单边下行，可能错失反转初期）

```json
{
  "conditions": [
    {"field": "mkt_weighted_slope_10m", "op": ">", "value": 0},
    {"field": "mkt_vwap_bias", "op": ">", "value": 0},
    {"field": "mkt_weighted_slope_2m", "op": ">", "value": 0.001}
  ]
}
```
- **效果**：只在大趋势向上+站稳VWAP时交易
- **代价**：反转日会延迟50-60秒入场

### 6.2 平衡型（杜绝下行 + 允许反转，推荐）

```json
{
  "conditions": [
    {"field": "mkt_new_low_distance", "op": ">", "value": 5},
    {"field": "mkt_weighted_slope_5m", "op": ">", "value": 0},
    {"field": "mkt_vwap_bias", "op": ">", "value": -0.1},
    {"field": "mkt_weighted_slope_2m", "op": ">", "value": 0.001}
  ]
}
```
- **效果**：停止创新低5分钟 + 中周期拐头 + 接近VWAP → 允许交易
- **代价**：反转后约3-5分钟确认入场

### 6.3 激进型（快速介入反转）

```json
{
  "conditions": [
    {"field": "mkt_new_low_distance", "op": ">", "value": 3},
    {"field": "mkt_day_position", "op": ">", "value": 20},
    {"field": "mkt_weighted_slope_2m", "op": ">", "value": 0.001}
  ]
}
```
- **效果**：3分钟没创新低+脱离底部区域 → 允许交易
- **代价**：可能捕捉到"假反转"

### 6.4 OR条件组合（推荐高阶用法）

```json
{
  "groups": [
    {
      "mode": "or",
      "subgroups": [
        {
          "name": "正常多头环境",
          "conditions": [
            {"field": "mkt_weighted_slope_10m", "op": ">", "value": 0},
            {"field": "mkt_vwap_bias", "op": ">", "value": 0}
          ]
        },
        {
          "name": "反转确认后",
          "conditions": [
            {"field": "mkt_new_low_distance", "op": ">", "value": 5},
            {"field": "mkt_weighted_slope_5m", "op": ">", "value": 0},
            {"field": "mkt_vwap_bias", "op": ">", "value": -0.1}
          ]
        }
      ]
    }
  ],
  "conditions": [
    {"field": "mkt_weighted_slope_2m", "op": ">", "value": 0.001},
    {"field": "weighted_slope_2m", "op": ">", "value": 0.005}
  ]
}
```
- **效果**：正常多头环境直接交易 OR 反转确认后也可交易
- **最优平衡**：既杜绝单边下行，又不错失反转行情

---

## 七、实施方案

### 7.1 改动文件

| 文件 | 改动内容 | 工作量 |
|------|---------|--------|
| `monitor_bond.py` | 新增6个全局变量 + `compute_mkt_trend_indicators()` 函数 | 中 |
| `backtest_bond.py` | `BACKTEST_FIELDS` 新增6个字段定义（json_field: True） | 小 |
| `quant_backtest.html` | 无需改动（BACKTEST_FIELDS驱动前端自动显示） | 无 |

### 7.2 计算开销

| 步骤 | 复杂度 | 耗时 |
|------|--------|------|
| mkt_vs_open_pct | O(N), pandas.mean() | <0.1ms |
| mkt_vwap_bias | O(1), 累加 | <0.01ms |
| mkt_weighted_slope_5m | O(K), K≈125 | ~1ms |
| mkt_weighted_slope_10m | O(K), K≈250 | ~2ms |
| mkt_day_position | O(1), 比较 | <0.01ms |
| mkt_new_low_distance | O(1), 减法 | <0.01ms |
| **总计** | — | **~3ms/tick** |

远低于3秒tick预算，对现有系统无性能影响。

### 7.3 内存开销

```
_mkt_slope_5m_cache:  125 ticks × 16 bytes = 2KB
_mkt_slope_10m_cache: 250 ticks × 16 bytes = 4KB
全局变量: ~50 bytes
总计: ~6KB（可忽略）
```

### 7.4 实施步骤

1. 在 `monitor_bond.py` 中新增全局变量和 `compute_mkt_trend_indicators()` 函数
2. 在现有 `compute_mkt_ext_indicators()` 调用位置后，调用新函数
3. 将6个新字段写入 `ext_indicators` JSON
4. 在 `backtest_bond.py` 的 `BACKTEST_FIELDS` 中新增6个字段定义
5. 回测验证：2026-07-13（单边下行）和正常日对比

---

## 八、设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 斜率算法 | EWLR（非OLS） | OLS 30分钟延迟10-15分钟，不可接受 |
| VWAP权重 | 成交额 `sum(amount)` | 反映资金方向，大资金操作权重高 |
| 5min half_life | 75s | 与2min(30s)保持2.5×关系，区分度明确 |
| 10min half_life | 150s | 与5min(75s)保持2×关系，层次分明 |
| 新低距离单位 | 分钟（float，1位小数） | 直觉清晰，与窗口参数(30分钟)单位一致 |
| 指标存储 | ext_indicators JSON | 与现有扩展指标一致，无数据库改动 |
| 前端展示 | BACKTEST_FIELDS驱动 | 无需额外前端开发 |

---

## 九、风险与注意事项

### 9.1 VWAP钝化问题

- 下午时VWAP累计了大量历史数据，对最新价格变化不敏感
- **对策**：用 `mkt_vwap_bias` 而非 VWAP 绝对值，偏离本身仍然灵敏

### 9.2 开盘初期不稳定

- 开盘前几分钟数据少，EWLR和高低点范围可能不准
- **对策**：建议入场条件中附加 `time > 09:35:00`（已有time_start参数）

### 9.3 横盘震荡的信号抖动

- 震荡市中 `mkt_vwap_bias` 会频繁穿越0
- **对策**：条件中设置小容忍度（如 > -0.05 而非 > 0），或配合 `mkt_weighted_slope_5m`

---

## 十、参考文档

- 《债券监控-斜率指标体系与滞后性解决方案》- EWLR算法详细规格
- 《债券趋势指标设计-双窗口斜率与放量高点偏离及日内高点距离》- 已有指标设计
- 《大盘趋势指标设计-基于全市场平均涨跌幅的市场级入场条件》- 大盘指标前期设计

---

*文档版本: v1.0*  
*最后更新: 2026-07-22*  
*状态: 待实施*
