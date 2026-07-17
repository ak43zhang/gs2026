# TickFlow获取data_gpsj_day数据方案

> 目标: 使用adata的TickFlow API获取股票日数据，生成与baostock同构的data_gpsj_day表

---

## 现状分析

### 可用API

| API | 返回数据 | 适用场景 |
|-----|---------|---------|
| `list_market_current` | 实时价格、涨跌幅、成交量、成交额 | 实时行情 |
| `get_market` | 历史日K线(OHLC) | 日数据（但当前返回空） |

### 数据字段对比

**目标表 data_gpsj_day 字段:**
```
stock_code, trade_time, trade_date, open, close, high, low, 
volume, amount, change_pct, change, turnover_ratio, pre_close
```

**list_market_current 返回:**
```
stock_code, short_name, price, change, change_pct, volume, amount
```

**缺失字段:**
- `open` - 开盘价
- `high` - 最高价  
- `low` - 最低价
- `pre_close` - 昨收（可推导: price - change）
- `turnover_ratio` - 换手率（需要流通股本）

---

## 方案设计

### 方案A: 组合API方案（推荐尝试）

使用 `get_market` 获取日K线数据（如果可用），否则降级到实时数据+昨日数据推导。

```python
class TickFlowSource:
    """TickFlow数据源 - 使用adata获取日数据"""
    
    def get_stock_data(self, stock_code: str, trade_date: str) -> Optional[pd.DataFrame]:
        """
        获取单只股票日数据
        
        策略:
        1. 优先使用 get_market 获取历史日K线
        2. 如果失败/为空，使用 list_market_current + 昨日数据推导
        """
        # 尝试1: 历史K线
        df = self._get_from_history(stock_code, trade_date)
        if df is not None and not df.empty:
            return df
        
        # 尝试2: 实时+昨日推导
        return self._get_from_realtime(stock_code, trade_date)
    
    def _get_from_history(self, stock_code, trade_date):
        """从历史K线获取"""
        try:
            df = adata.stock.market.get_market(
                stock_code=stock_code,
                start_date=trade_date,
                end_date=trade_date,
                k_type=1,        # 日K
                adjust_type=1    # 前复权
            )
            if df is not None and not df.empty:
                return self._transform_history(df, stock_code)
        except Exception as e:
            logger.warning(f"历史K线获取失败 {stock_code}: {e}")
        return None
    
    def _get_from_realtime(self, stock_code, trade_date):
        """从实时数据+昨日数据推导"""
        # 获取实时数据
        df_rt = adata.stock.market.list_market_current([stock_code])
        if df_rt is None or df_rt.empty:
            return None
        
        # 获取昨日数据（用于推导open/high/low）
        prev_date = self._get_prev_trade_date(trade_date)
        df_prev = self._get_from_history(stock_code, prev_date)
        
        # 合并推导
        return self._transform_realtime(df_rt, df_prev, stock_code, trade_date)
```

### 方案B: 从Monitor表同步（稳妥方案）

如果盘中已有monitor数据，可以直接从 `monitor_gp_sssj_{date}` 表转换：

```python
def create_from_monitor_sssj(date: str):
    """
    从monitor实时数据表创建data_gpsj_day
    
    取当日最后一笔数据作为日数据
    """
    sql = f"""
    INSERT INTO data_gpsj_day_{date}
    SELECT 
        NULL as `index`,
        stock_code,
        CONCAT('{date[:4]}-{date[4:6]}-{date[6:]}', ' 00:00:00') as trade_time,
        '{date[:4]}-{date[4:6]}-{date[6:]}' as trade_date,
        open,
        price as close,
        high,
        low,
        volume,
        amount,
        change_pct,
        change,
        turnover_ratio,
        pre_close
    FROM monitor_gp_sssj_{date}
    WHERE time = (SELECT MAX(time) FROM monitor_gp_sssj_{date})
    """
```

### 方案C: 使用问财/其他数据源

如果adata不可用，可以尝试：
- wencai (同花顺问财)
- tushare (需付费)
- 东方财富直接爬取

---

## 推荐实施方案

### 短期: 方案B（从Monitor同步）

**原因**: 
- 立即可用，无需外部API
- monitor数据已包含OHLC
- 数据质量有保障

**实施步骤**:
1. 创建 `tickflow_to_daily.py` 脚本
2. 从 `monitor_gp_sssj_{date}` 读取最后一笔数据
3. 转换并写入 `data_gpsj_day_{date}`

### 长期: 方案A（修复adata get_market）

**需要排查**:
- 为什么 `get_market` 返回空数据
- 日期格式是否正确
- 是否需要特定参数

---

## 字段映射详情

### list_market_current → data_gpsj_day

| 目标字段 | 来源 | 转换逻辑 |
|---------|------|---------|
| stock_code | stock_code | 直接映射 |
| trade_time | trade_date + ' 00:00:00' | 拼接 |
| trade_date | trade_date | YYYY-MM-DD |
| open | 需推导 | 用昨日close或今日第一笔 |
| close | price | 直接映射 |
| high | 需推导 | 用今日max(price) |
| low | 需推导 | 用今日min(price) |
| volume | volume | 直接映射（需确认单位） |
| amount | amount | 直接映射 |
| change_pct | change_pct | 直接映射 |
| change | change | 直接映射 |
| turnover_ratio | 需计算 | amount / (流通股本 * close) |
| pre_close | price - change | 推导 |

---

## 验证步骤

1. 采集2026-04-23数据
2. 对比字段完整性
3. 对比数值准确性（与baostock历史数据对比）
4. 下游功能验证（涨停行概选股等）

---

**方案状态**: 待审核
