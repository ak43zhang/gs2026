# 股票日数据采集模块重构设计方案

**设计时间**: 2026-03-30 05:11  
**目标**: 使用 AKShare/ADATA 替代 Baostock，解决接口无响应问题

---

## 一、现状分析

### 1.1 当前表结构 (data_gpsj_day_YYYYMMDD)

| 字段名 | 类型 | 说明 | 数据源字段 |
|--------|------|------|-----------|
| index | bigint | 自增索引 | 自动生成 |
| stock_code | text | 股票代码 | 600000 |
| trade_time | text | 交易时间 | 2026-03-16 00:00:00 |
| trade_date | text | 交易日期 | 2026-03-16 |
| open | double | 开盘价 | 10.93 |
| close | double | 收盘价 | 10.92 |
| high | double | 最高价 | 10.97 |
| low | double | 最低价 | 10.88 |
| volume | double | 成交量 | 71560300.0 |
| amount | double | 成交额 | 782089440.63 |
| change_pct | double | 涨跌幅(%) | -0.09 |
| change | double | 涨跌额 | -0.01 |
| turnover_ratio | double | 换手率(%) | 0.37 |
| pre_close | double | 昨收价 | 10.93 |

### 1.2 当前逻辑分析 (baostock_collection.py)

**流程**:
1. 从数据库获取股票代码列表 (AG_STOCK_SQL5)
2. 登录 Baostock
3. 逐只股票查询 (query_history_k_data_plus)
4. 数据转换 (字段映射、类型转换)
5. 逐条插入 MySQL

**问题**:
- Baostock 接口无响应
- 逐条插入效率低
- 无批量处理

---

## 二、数据源对比

### 2.1 AKShare (推荐)

**优点**:
- ✅ 免费、开源、活跃维护
- ✅ 接口稳定、响应快
- ✅ 数据丰富、字段齐全
- ✅ 支持批量查询

**缺点**:
- 需要处理反爬限制
- 部分接口有频率限制

**接口**:
```python
import akshare as ak
# 单只股票历史行情
ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20260301", end_date="20260330", adjust="qfq")
# 批量获取需要循环
```

### 2.2 ADATA (新兴)

**优点**:
- ✅ 免费、轻量级
- ✅ 接口简洁
- ✅ 支持A股全市场

**缺点**:
- 相对较新，稳定性待验证
- 功能相对简单

**接口**:
```python
import adata
# 历史行情
adata.stock.get_market(stock_code="000001", start_date="2026-03-01", end_date="2026-03-30")
```

---

## 三、设计方案

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    stock_daily_collection.py                 │
│                      (统一入口模块)                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  akshare_source  │  │  adata_source    │                │
│  │  (AKShare数据源) │  │  (ADATA数据源)   │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           │                     │                           │
│           └──────────┬──────────┘                           │
│                      │                                      │
│           ┌──────────▼──────────┐                          │
│           │   data_transform    │                          │
│           │   (数据转换标准化)   │                          │
│           └──────────┬──────────┘                          │
│                      │                                      │
│           ┌──────────▼──────────┐                          │
│           │   batch_insert      │                          │
│           │   (批量入库优化)     │                          │
│           └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
src/gs2026/collection/base/
├── baostock_collection.py          # 原Baostock模块（保留备用）
├── stock_daily_collection.py       # 统一入口（新）
├── akshare_source.py               # AKShare数据源（新）
├── adata_source.py                 # ADATA数据源（新）
└── data_transform.py               # 数据转换工具（新）
```

### 3.3 核心模块设计

#### 3.3.1 stock_daily_collection.py (统一入口)

```python
"""
股票日数据采集统一入口
支持多数据源: akshare, adata
"""
import time
from typing import Optional, Literal
from loguru import logger

from gs2026.utils import mysql_util, config_util, string_enum
from gs2026.collection.base import akshare_source, adata_source

DataSource = Literal['akshare', 'adata', 'baostock']

class StockDailyCollector:
    """股票日数据采集器"""
    
    def __init__(self, data_source: DataSource = 'akshare'):
        self.data_source = data_source
        self.source = self._init_source()
    
    def _init_source(self):
        """初始化数据源"""
        if self.data_source == 'akshare':
            return akshare_source.AKShareSource()
        elif self.data_source == 'adata':
            return adata_source.ADataSource()
        else:
            raise ValueError(f"不支持的数据源: {self.data_source}")
    
    def collect(self, start_date: str, end_date: str, batch_size: int = 100) -> None:
        """
        采集股票日数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            batch_size: 批量插入大小
        """
        logger.info(f"使用数据源: {self.data_source}, 日期: {start_date} ~ {end_date}")
        
        # 1. 获取交易日列表
        trade_dates = self._get_trade_dates(start_date, end_date)
        
        for trade_date in trade_dates:
            self._collect_single_day(trade_date, batch_size)
    
    def _collect_single_day(self, trade_date: str, batch_size: int) -> None:
        """采集单日数据"""
        table_name = f'data_gpsj_day_{trade_date.replace("-", "")}'
        
        # 1. 获取股票代码列表
        stock_codes = self._get_stock_codes()
        logger.info(f"日期: {trade_date}, 股票数: {len(stock_codes)}")
        
        # 2. 批量采集
        all_data = []
        for i, code in enumerate(stock_codes):
            df = self.source.get_stock_data(code, trade_date, trade_date)
            if df is not None and not df.empty:
                all_data.append(df)
                
                # 批量插入
                if len(all_data) >= batch_size:
                    self._batch_insert(all_data, table_name)
                    logger.info(f"已插入 {i+1}/{len(stock_codes)}")
                    all_data = []
        
        # 3. 插入剩余数据
        if all_data:
            self._batch_insert(all_data, table_name)
        
        logger.info(f"日期 {trade_date} 采集完成")
    
    def _batch_insert(self, dataframes: list, table_name: str) -> None:
        """批量插入数据"""
        import pandas as pd
        from sqlalchemy import create_engine
        
        combined = pd.concat(dataframes, ignore_index=True)
        
        url = config_util.get_config("common.url")
        engine = create_engine(url, pool_recycle=3600)
        
        with engine.begin() as conn:
            combined.to_sql(
                name=table_name,
                con=conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
```

#### 3.3.2 akshare_source.py (AKShare数据源)

```python
"""
AKShare 数据源适配器
"""
import time
import akshare as ak
import pandas as pd
from typing import Optional
from loguru import logger


class AKShareSource:
    """AKShare数据源"""
    
    # 字段映射: AKShare字段 -> 目标字段
    FIELD_MAPPING = {
        '股票代码': 'stock_code',
        '日期': 'trade_date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '振幅': 'amplitude',
        '涨跌幅': 'change_pct',
        '涨跌额': 'change',
        '换手率': 'turnover_ratio',
    }
    
    def __init__(self):
        self.request_delay = 0.1  # 请求间隔，防止反爬
    
    def get_stock_data(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        获取单只股票历史数据
        
        Args:
            stock_code: 股票代码 (如: 600000)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        
        Returns:
            DataFrame或None
        """
        try:
            # 转换日期格式
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")
            
            # 调用AKShare接口
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                logger.warning(f"AKShare: {stock_code} 无数据")
                return None
            
            # 数据转换
            result = self._transform_data(df, stock_code)
            
            # 请求间隔
            time.sleep(self.request_delay)
            
            return result
            
        except Exception as e:
            logger.error(f"AKShare获取 {stock_code} 失败: {e}")
            return None
    
    def _transform_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """转换数据格式"""
        # 重命名字段
        df = df.rename(columns=self.FIELD_MAPPING)
        
        # 添加trade_time
        df['trade_time'] = df['trade_date'] + ' 00:00:00'
        
        # 计算pre_close
        df['pre_close'] = df['close'] - df['change']
        
        # 确保stock_code正确
        df['stock_code'] = stock_code
        
        # 类型转换和精度处理
        numeric_cols = ['open', 'close', 'high', 'low', 'volume', 'amount', 
                       'change_pct', 'change', 'turnover_ratio', 'pre_close']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        
        # 成交量处理（转换为股）
        if 'volume' in df.columns:
            df['volume'] = (df['volume'] * 100).astype(int)  # 手 -> 股
        
        # 选择目标字段
        target_cols = ['stock_code', 'trade_time', 'trade_date', 'open', 'close', 
                      'high', 'low', 'volume', 'amount', 'change_pct', 'change',
                      'turnover_ratio', 'pre_close']
        
        return df[[col for col in target_cols if col in df.columns]]
    
    def get_all_stocks(self) -> list:
        """获取所有A股代码列表"""
        try:
            df = ak.stock_zh_a_spot_em()
            return df['代码'].tolist()
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
```

#### 3.3.3 adata_source.py (ADATA数据源)

```python
"""
ADATA 数据源适配器
"""
import time
import adata
import pandas as pd
from typing import Optional
from loguru import logger


class ADataSource:
    """ADATA数据源"""
    
    # 字段映射: ADATA字段 -> 目标字段
    FIELD_MAPPING = {
        'stock_code': 'stock_code',
        'trade_date': 'trade_date',
        'open': 'open',
        'close': 'close',
        'high': 'high',
        'low': 'low',
        'volume': 'volume',
        'amount': 'amount',
        'change': 'change',
        'change_pct': 'change_pct',
        'turnover_ratio': 'turnover_ratio',
    }
    
    def __init__(self):
        self.request_delay = 0.05
    
    def get_stock_data(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取单只股票历史数据"""
        try:
            df = adata.stock.get_market(
                stock_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                return None
            
            # 数据转换
            result = self._transform_data(df, stock_code)
            
            time.sleep(self.request_delay)
            return result
            
        except Exception as e:
            logger.error(f"ADATA获取 {stock_code} 失败: {e}")
            return None
    
    def _transform_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """转换数据格式"""
        # 重命名
        df = df.rename(columns=self.FIELD_MAPPING)
        
        # 添加trade_time
        df['trade_time'] = df['trade_date'] + ' 00:00:00'
        
        # 计算pre_close（如果没有）
        if 'pre_close' not in df.columns:
            df['pre_close'] = df['close'] - df['change']
        
        # 确保stock_code
        df['stock_code'] = stock_code
        
        # 类型转换
        numeric_cols = ['open', 'close', 'high', 'low', 'volume', 'amount',
                       'change_pct', 'change', 'turnover_ratio', 'pre_close']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        
        # 选择目标字段
        target_cols = ['stock_code', 'trade_time', 'trade_date', 'open', 'close',
                      'high', 'low', 'volume', 'amount', 'change_pct', 'change',
                      'turnover_ratio', 'pre_close']
        
        return df[[col for col in target_cols if col in df.columns]]
```

---

## 四、关键优化点

### 4.1 批量插入优化

```python
def batch_insert(dataframes: list, table_name: str, batch_size: int = 100):
    """批量插入，替代逐条插入"""
    combined = pd.concat(dataframes, ignore_index=True)
    
    with engine.begin() as conn:
        combined.to_sql(
            name=table_name,
            con=conn,
            if_exists='append',
            index=False,
            method='multi',      # 使用多值INSERT
            chunksize=1000       # 每1000条执行一次
        )
```

**性能提升**: 50-100倍

### 4.2 并发采集优化

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def collect_concurrent(self, trade_date: str, max_workers: int = 5):
    """并发采集"""
    stock_codes = self._get_stock_codes()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(self.source.get_stock_data, code, trade_date, trade_date): code 
            for code in stock_codes
        }
        
        for future in as_completed(futures):
            code = futures[future]
            df = future.result()
            if df is not None:
                # 批量插入
```

**性能提升**: 5-10倍

### 4.3 错误处理和重试

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def get_stock_data_with_retry(self, stock_code: str, start_date: str, end_date: str):
    """带重试的数据获取"""
    return self.get_stock_data(stock_code, start_date, end_date)
```

---

## 五、实施计划

### 阶段1: 基础模块开发 (2小时)
- [ ] akshare_source.py - AKShare数据源
- [ ] adata_source.py - ADATA数据源
- [ ] data_transform.py - 数据转换工具

### 阶段2: 统一入口开发 (1小时)
- [ ] stock_daily_collection.py - 统一采集入口
- [ ] 批量插入优化
- [ ] 错误处理

### 阶段3: 测试验证 (1小时)
- [ ] 单只股票测试
- [ ] 批量采集测试
- [ ] 性能对比测试

### 阶段4: 集成部署 (30分钟)
- [ ] Dashboard2 集成
- [ ] 配置更新
- [ ] 监控告警

---

## 六、使用方式

### 6.1 命令行使用

```python
# 使用AKShare采集
from gs2026.collection.base.stock_daily_collection import StockDailyCollector

collector = StockDailyCollector(data_source='akshare')
collector.collect(start_date='2026-03-01', end_date='2026-03-30')

# 使用ADATA采集
collector = StockDailyCollector(data_source='adata')
collector.collect(start_date='2026-03-01', end_date='2026-03-30')
```

### 6.2 Dashboard2 集成

```python
# 在collection.py中添加
from gs2026.collection.base.stock_daily_collection import StockDailyCollector

def start_stock_daily_collection(start_date: str, end_date: str):
    collector = StockDailyCollector(data_source='akshare')
    collector.collect(start_date, end_date)
```

---

## 七、预期效果

| 指标 | 当前(Baostock) | 优化后(AKShare) | 提升 |
|------|---------------|----------------|------|
| 接口响应 | 超时无响应 | 正常 | ✅ 可用 |
| 采集速度 | 83分钟 | 10分钟 | 8倍 |
| 插入速度 | 101条/秒 | 5000+条/秒 | 50倍 |
| 成功率 | 0% | 95%+ | ✅ 稳定 |

---

**请确认方案后开发实施。**
