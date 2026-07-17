# 效果追踪功能 - 完整设计文档

## 功能概述

为买点候选记录生成效果追踪数据，同时追踪**股票**和**关联债券**在信号发出后的涨跌表现。支持日期选择、分段统计（股票/债券独立）、明细结果展示。

## 核心特性

- 同时追踪股票和债券的效果
- 4个时间区间：5分钟/15分钟/30分钟/收盘
- 每个区间展示**绝对涨跌幅**和**相对涨跌幅**（双列）
- 分段统计：总数/成功/失败/胜率/均收（基于**相对涨跌幅**计算）
- 支持历史日期选择
- 支持星级筛选（⭐⭐⭐、⭐⭐、⭐）
- 自动检测并创建数据库字段
- 固定表头（滚动时列名不动）
- 统计区域高度优化，明细结果占更多空间
- 明细结果按时间顺序排序（从早到晚）

---

## 数据流

```
buy_point_candidates 表
    |
    +-- stock_code + stock_price + time + stock_change_pct (股票信号)
    |       |
    |       v
    |   monitor_gp_sssj_{date} 表
    |       |  批量查询: SELECT code, time, price WHERE code IN (...)
    |       v
    |   计算股票绝对涨跌幅
    |       +-- 昨日收盘价 = signal_price / (1 + signal_change_pct/100)
    |       +-- 5m绝对:  (price@time+5m - pre_close) / pre_close * 100%
    |       +-- 15m绝对: (price@time+15m - pre_close) / pre_close * 100%
    |       +-- 30m绝对: (price@time+30m - pre_close) / pre_close * 100%
    |       +-- close绝对: (close_price - pre_close) / pre_close * 100%
    |       +-- 相对值 = 绝对值 - signal_change_pct
    |
    +-- bond_code + bond_price + time + bond_change_pct (债券信号)
    |       |
    |       v
    |   monitor_zq_sssj_{date} 表
    |       |  批量查询: SELECT code, time, price WHERE code IN (...)
    |       v
    |   计算债券绝对涨跌幅（同股票逻辑）
    |
    v
分段统计 (股票独立 + 债券独立)
    +-- 股票: 总数/成功/失败/胜率/均收 x 4个区间（基于相对值）
    +-- 债券: 总数/失败/失败/胜率/均收 x 4个区间（基于相对值）
```

---

## 数据库设计

### 现有字段（股票效果）

| 字段 | 类型 | 说明 |
|------|------|------|
| after_5m_price | DECIMAL(10,2) | 5分钟后股票价格 |
| after_5m_change_pct | DECIMAL(6,4) | 5分钟后股票涨跌幅%（绝对） |
| after_15m_price | DECIMAL(10,2) | 15分钟后股票价格 |
| after_15m_change_pct | DECIMAL(6,4) | 15分钟后股票涨跌幅%（绝对） |
| after_30m_price | DECIMAL(10,2) | 30分钟后股票价格 |
| after_30m_change_pct | DECIMAL(6,4) | 30分钟后股票涨跌幅%（绝对） |
| after_close_price | DECIMAL(10,2) | 收盘时股票价格 |
| after_close_change_pct | DECIMAL(6,4) | 收盘时股票涨跌幅%（绝对） |
| stock_change_pct | DECIMAL(6,4) | 信号时股票涨跌幅%（命中） |

### 新增字段（债券效果）

| 字段 | 类型 | 说明 |
|------|------|------|
| bond_after_5m_price | DECIMAL(10,3) | 5分钟后债券价格 |
| bond_after_5m_change_pct | DECIMAL(6,4) | 5分钟后债券涨跌幅%（绝对） |
| bond_after_15m_price | DECIMAL(10,3) | 15分钟后债券价格 |
| bond_after_15m_change_pct | DECIMAL(6,4) | 15分钟后债券涨跌幅%（绝对） |
| bond_after_30m_price | DECIMAL(10,3) | 30分钟后债券价格 |
| bond_after_30m_change_pct | DECIMAL(6,4) | 30分钟后债券涨跌幅%（绝对） |
| bond_after_close_price | DECIMAL(10,3) | 收盘时债券价格 |
| bond_after_close_change_pct | DECIMAL(6,4) | 收盘时债券涨跌幅%（绝对） |
| bond_change_pct | DECIMAL(6,4) | 信号时债券涨跌幅%（命中） |

---

## 关键算法

### 绝对涨跌幅计算

```python
# 昨日收盘价 = 信号价格 / (1 + 信号涨跌幅/100)
pre_close = signal_price / (1 + signal_change_pct / 100)

# 绝对涨跌幅 = (时间点价格 - 昨日收盘价) / 昨日收盘价 * 100
abs_change_pct = (time_price - pre_close) / pre_close * 100
```

### 相对涨跌幅计算

```python
# 相对涨跌幅 = 绝对涨跌幅 - 信号时涨跌幅
rel_change_pct = abs_change_pct - signal_change_pct
```

### 统计计算

```python
# 成功 = 相对涨跌幅 > 0
# 失败 = 相对涨跌幅 <= 0
# 胜率 = 成功数 / 总数 * 100
# 均收 = 平均相对涨跌幅
```

---

## API设计

### POST /api/monitor/buy-points/generate-effects

**请求**:
```json
{"date": "20260522", "levels": [1, 2, 3]}
```

**响应**:
```json
{
    "success": true,
    "filled": 120,
    "skipped": 0,
    "stats": {
        "stock": {
            "5m":    {"total": 87, "success": 0, "fail": 87, "success_rate": 0, "avg_return": -5.23},
            "15m":   {"total": 84, "success": 5, "fail": 79, "success_rate": 6, "avg_return": -3.15},
            "30m":   {"total": 82, "success": 12, "fail": 70, "success_rate": 15, "avg_return": -1.80},
            "close": {"total": 80, "success": 35, "fail": 45, "success_rate": 44, "avg_return": 0.50}
        },
        "bond": {
            "5m":    {"total": 85, "success": 15, "fail": 70, "success_rate": 18, "avg_return": -0.85},
            "15m":   {"total": 83, "success": 25, "fail": 58, "success_rate": 30, "avg_return": 0.20},
            "30m":   {"total": 81, "success": 35, "fail": 46, "success_rate": 43, "avg_return": 0.60},
            "close": {"total": 79, "success": 56, "fail": 23, "success_rate": 71, "avg_return": 1.50}
        }
    },
    "details": [
        {
            "time": "09:34:06",
            "code": "002859",
            "name": "洁美科技",
            "bond_code": "128137",
            "level": 3,
            "stock_signal_price": 28.50,
            "stock_signal_change_pct": 4.91,
            "stock_5m": 2.06,
            "stock_15m": 3.63,
            "stock_30m": 1.64,
            "stock_close": 4.85,
            "bond_signal_price": 145.20,
            "bond_signal_change_pct": 5.24,
            "bond_5m": 1.69,
            "bond_15m": 3.25,
            "bond_30m": 2.80,
            "bond_close": 5.72
        }
    ]
}
```

---

## 前端UI设计

### 页面位置

**分析中心 → 回溯分析 → 效果追踪** 标签页

### 布局结构

```
+----------------------------------------------------------+
|  回溯分析                                    [返回]      |
|  +--------------------------------------------------+    |
|  | 回溯记录 | 效果追踪 | 条件分析 | 策略优化 |       |    |
|  +--------------------------------------------------+    |
|                                                          |
|  日期: [2026-05-22]  星级: [⭐⭐⭐] [⭐⭐] [⭐] [生成效果] |
|                                                          |
|  +------------------+  +------------------+             |
|  | 股票效果统计      |  | 债券效果统计      |             |
|  +------------------+  +------------------+             |
|                                                          |
|  +--------------------------------------------------+    |
|  | 明细结果                                          |    |
|  | +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+ |    |
|  | |时|代|名|⭐|信|命|  5m  | 15m | 30m | 收盘 |债命| 5m  |    |
|  | |间|码|称|级|号|中|绝|相|绝|相|绝|相|绝|相|    |绝|相|    |
|  | +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+ |    |
|  | |9:|00|洁|⭐|28|4.|2.| - |3.| - |1.| - |4.| - |5.|1.| - |    |
|  | |34|28|美|⭐|50|91|06|2.8|63|1.2|64|3.2|85|0.0|24|69|3.5|    |
|  | +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+ |    |
|  +--------------------------------------------------+    |
+----------------------------------------------------------+
```

### 明细表格列结构（19列）

| 列 | 内容 | 背景色 |
|---|------|--------|
| 1 | 时间 | - |
| 2 | 代码 | - |
| 3 | 名称 | - |
| 4 | ⭐ | - |
| 5 | 信号价 | - |
| 6 | 股票命中 | #ffe4e1（浅红） |
| 7-8 | 5m 绝/相 | #fff5f5（淡红） |
| 9-10 | 15m 绝/相 | #fff5f5（淡红） |
| 11-12 | 30m 绝/相 | #fff5f5（淡红） |
| 13-14 | 收盘 绝/相 | #fff5f5（淡红） |
| 15 | 债券命中 | #e1f5fe（浅蓝） |
| 16-17 | 债券5m 绝/相 | #f5f8ff（淡蓝） |
| 18-19 | 债券收盘 绝/相 | #f5f8ff（淡蓝） |

*注：实际展示23列（包含债券15m、30m）*

### 样式特性

1. **固定表头**：`position: sticky; top: 0; z-index: 10`
2. **完整边框**：所有单元格带边框
3. **颜色区分**：
   - 正值：红色 `#e53935`
   - 负值：绿色 `#43a047`
   - 零值：灰色 `#666`
4. **统计区域高度**：`padding: 6px 10px`（紧凑）
5. **排序**：按时间 ASC（从早到晚）

---

## 改动清单

### 后端改动

| 文件 | 改动 | 说明 |
|------|------|------|
| routes/monitor.py | 修改 `generate_effects()` | 同时查询股票+债券sssj数据，计算绝对涨跌幅 |
| routes/monitor.py | 修改 `_batch_get_sssj_prices()` | 只获取price，用于计算绝对涨跌幅 |
| routes/monitor.py | 新增 `_find_nearest_price()` | 找最近时间点的价格 |
| routes/monitor.py | 新增 `_find_close_price()` | 取收盘价格 |
| routes/monitor.py | 新增 `_find_nearest_change_pct()` | 备用：找最近时间点的涨跌幅 |
| routes/monitor.py | 新增 `_find_close_change_pct()` | 备用：取收盘涨跌幅 |
| routes/monitor.py | 新增 `_calc_effect_stats()` | 计算分段统计（股票/债券独立） |
| routes/monitor.py | 修改 `_ensure_effect_columns()` | 同时检测并添加股票+债券效果字段 |

### 前端改动

| 文件 | 改动 | 说明 |
|------|------|------|
| templates/backtest.html | 新增效果追踪标签页 | 从monitor.html迁移并增强 |
| templates/backtest.html | 修改头部链接 | `/ztb-analysis` → `/analysis/backtest` |
| templates/backtest.html | 新增星级筛选 | ⭐⭐⭐、⭐⭐、⭐ 复选框 |
| templates/backtest.html | 新增日期选择器 | `input type="date"` |
| templates/backtest.html | 新增 `generateTracking()` | 生成效果并展示 |
| templates/backtest.html | 新增 `recalcStats()` | 根据明细重新计算统计（基于相对值） |
| templates/backtest.html | 新增 `calcPeriodStats()` | 计算单个时段统计 |
| templates/backtest.html | 新增 `renderTrackingStats()` | 渲染股票+债券统计 |
| templates/backtest.html | 新增 `buildStatsHtml()` | 构建统计表格HTML |
| templates/backtest.html | 新增 `renderTrackingDetails()` | 渲染23列明细表格 |
| templates/backtest.html | 新增固定表头样式 | `position: sticky` |
| templates/backtest.html | 新增边框样式 | 完整表格边框 |

---

## 注意事项

1. **绝对值 vs 相对值**：
   - 绝对值 = 相对于昨日收盘价的涨跌幅
   - 相对值 = 绝对值 - 信号时涨跌幅（相对于信号时的收益）

2. **统计基于相对值**：
   - 成功 = 相对值 > 0（即后续涨幅超过信号时）
   - 失败 = 相对值 <= 0

3. **数据缺失处理**：
   - 无sssj数据：显示 "-"
   - 无债券关联：债券列显示 "-"
   - 时间超出交易时段：该时段为null

4. **午休调整**：
   - 11:30-13:00为午休
   - 时间计算自动调整：13:00后的时间 = 实际时间 + 1.5小时

5. **性能优化**：
   - 批量查询sssj数据（非逐条）
   - 前端移除二次过滤（后端已按星级过滤）

---

## 问题修复记录

### 2026-05-25 修复

1. **修复绝对涨跌幅计算**（v2.0）
   - 问题：`sssj`表的`change_pct`字段值不正确
   - 修复：改用价格计算绝对涨跌幅
   - 公式：`pre_close = signal_price / (1 + signal_change_pct/100)`

2. **修复统计为0问题**（v2.1）
   - 问题：前端二次过滤导致数据丢失
   - 修复：移除前端过滤，直接使用后端返回的details

3. **修复返回404问题**（v2.2）
   - 问题：头部链接指向`/ztb-analysis`
   - 修复：改为`/analysis/backtest`

4. **修复表格列数**（v2.3）
   - 问题：缺少债券命中列
   - 修复：添加债券命中列（浅蓝底），总列数23列

---

*文档版本: 2.3*
*最后更新: 2026-05-25 02:17*
