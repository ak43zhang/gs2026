# Baostock替代方案 - 使用AKShare/AData采集data_gpsj_day数据

> 问题: baostock登录失败，无法采集`data_gpsj_day_{date}`数据
> 目标: 修改`combine_collection.py`调用链，使用现有的`stock_daily_collection.py`替代

---

## 问题分析

### 现状

1. **baostock登录失败** → `data_gpsj_day_20260423` 表未创建
2. 调用链: `combine_collection.py:125` → `baostock_collection.get_baostock_collection()`
3. 已有替代方案 `stock_daily_collection.py`（支持akshare/adata），但未被主流程使用

### data_gpsj_day表结构

```sql
CREATE TABLE data_gpsj_day_20260421 (
  `index` bigint DEFAULT NULL,        -- pandas自动生成的行号
  `stock_code` text,                   -- 股票代码 (如: 000001)
  `trade_time` text,                   -- 交易时间 (如: 2026-04-21 00:00:00)
  `trade_date` text,                   -- 交易日期 (如: 2026-04-21)
  `open` double DEFAULT NULL,          -- 开盘价
  `close` double DEFAULT NULL,         -- 收盘价
  `high` double DEFAULT NULL,          -- 最高价
  `low` double DEFAULT NULL,           -- 最低价
  `volume` double DEFAULT NULL,        -- 成交量（股）
  `amount` double DEFAULT NULL,        -- 成交额（元）
  `change_pct` double DEFAULT NULL,    -- 涨跌幅（%）
  `change` double DEFAULT NULL,        -- 涨跌额（元）
  `turnover_ratio` double DEFAULT NULL,-- 换手率（%）
  `pre_close` double DEFAULT NULL      -- 昨收价
)
```

### 数据样例

```
stock_code  trade_time            trade_date  open   close  high   low    volume      amount       change_pct  change  turnover_ratio  pre_close
000001      2026-04-21 00:00:00  2026-04-21  11.04  11.08  11.16  11.03  80694600.0  8.97e+08     0.18        0.02    0.42            11.06
000002      2026-04-21 00:00:00  2026-04-21   3.92   3.90   3.95   3.89  72886800.0  2.85e+08    -0.76       -0.03    0.75             3.93
```

### 字段差异分析

| 字段 | baostock原版 | stock_daily_collection(akshare) | 差异 |
|------|-------------|--------------------------------|------|
| index | ✅ to_sql自动生成 | ❌ index=False | **需要修改** |
| stock_code | ✅ 6位字符串 | ✅ 6位字符串 | 一致 |
| trade_time | ✅ YYYY-MM-DD HH:MM:SS | ✅ YYYY-MM-DD 00:00:00 | 一致 |
| trade_date | ✅ YYYY-MM-DD | ✅ YYYY-MM-DD | 一致 |
| open/close/high/low | ✅ float | ✅ float | 一致 |
| volume | ✅ 股（整百） | ⚠️ 手×100转股 | **需确认** |
| amount | ✅ 元 | ✅ 元 | 一致 |
| change_pct | ✅ % | ✅ % | 一致 |
| change | ✅ 元 | ✅ 元 | 一致 |
| turnover_ratio | ✅ % | ✅ % | 一致 |
| pre_close | ✅ 元 | ✅ 元 | 一致 |

---

## 修复方案

### 修改1: `combine_collection.py` - 替换baostock调用

```python
# 修改前（第125行）
baostock_collection.get_baostock_collection(start_time, end_time)

# 修改后
from gs2026.collection.base.stock_daily_collection import collect_stock_daily
collect_stock_daily(start_time, end_time, data_source='akshare', batch_size=100)
```

### 修改2: `stock_daily_collection.py` - 兼容baostock的to_sql行为

baostock原版使用 `df.to_sql(..., if_exists='append')` 不带 `index=False`，所以表中有 `index` 列。
`stock_daily_collection.py` 使用 `index=False`，不会生成 `index` 列。

**需要确认**: 下游代码是否依赖 `index` 列？

经分析，`index` 列是pandas自动生成的行号，不含业务意义。下游代码不依赖此列。因此 `stock_daily_collection.py` 的 `index=False` 是正确的（更干净）。

### 修改3: `akshare_source.py` - 确保volume单位正确

AKShare的 `stock_zh_a_hist` 返回的成交量单位是"手"，当前代码已做了 `volume * 100` 转换为"股"。

但baostock原版还做了 `(volume // 100) * 100` 整百处理。为保持一致，需要在akshare_source中也做整百处理。

```python
# akshare_source.py - _transform_data 中
if 'volume' in df.columns:
    df['volume'] = ((df['volume'] * 100) // 100) * 100  # 手→股，整百
```

### 修改4: 添加数据源降级机制

akshare失败时自动降级到adata：

```python
def collect_stock_daily_with_fallback(start_date, end_date, batch_size=100):
    """带降级的采集入口"""
    try:
        collect_stock_daily(start_date, end_date, data_source='akshare', batch_size=batch_size)
    except Exception as e:
        logger.warning(f"AKShare采集失败，降级到AData: {e}")
        collect_stock_daily(start_date, end_date, data_source='adata', batch_size=batch_size)
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `combine_collection.py` | 替换baostock调用为stock_daily_collection |
| `akshare_source.py` | volume整百处理 |
| `stock_daily_collection.py` | 添加降级入口函数 |

---

## 验证步骤

1. 运行 `stock_daily_collection.py` 采集今天(20260423)的数据
2. 检查 `data_gpsj_day_20260423` 表是否创建成功
3. 对比新表与旧表(20260421)的数据结构是否一致
4. 验证下游功能（涨停行概选股等）是否正常

---

**方案状态**: 待审核
