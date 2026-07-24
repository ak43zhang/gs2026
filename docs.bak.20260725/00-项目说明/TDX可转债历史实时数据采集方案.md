# TDX历史实时可转债数据采集方案

## 需求概述

通过 TDX 接口采集历史实时可转债数据，按日期生成 MySQL 表，表名为 `base_bond_data_{yyyyMMdd}`。

## 设计方案

### 1. 核心功能模块

```
src/gs2026/collection/base/
├── bond_tdx_collector.py      # 【新增】TDX可转债历史实时数据采集器
└── (其他已有文件)
```

### 2. 类设计

```python
class BondTDXCollector:
    """
    TDX可转债历史实时数据采集器
    
    功能：
    1. 通过TDX接口获取历史实时数据（1分钟K线）
    2. 按日期生成MySQL表 base_bond_data_{yyyyMMdd}
    3. 支持日期范围采集（借鉴量化回测的交易日获取）
    """
    
    def __init__(self):
        self.engine = config_util.get_engine()
        self.mysql_tool = mysql_util.get_mysql_tool()
        self.tdx_api = None  # TDX连接缓存
    
    def collect(self, start_date: str, end_date: str) -> None:
        """
        采集指定日期范围的债券历史实时数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        # 1. 获取交易日列表（从data_jyrl表）
        trade_dates = self._get_trade_dates(start_date, end_date)
        
        # 2. 遍历每个交易日采集
        for trade_date in trade_dates:
            self._collect_single_day(trade_date)
    
    def _get_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """从data_jyrl获取交易日列表（借鉴stock_daily_collection.py）"""
        sql = """
            SELECT trade_date 
            FROM data_jyrl 
            WHERE trade_date BETWEEN %s AND %s 
              AND trade_status = '1' 
            ORDER BY trade_date
        """
        df = pd.read_sql(sql, self.engine, params=[start_date, end_date])
        return df['trade_date'].tolist()
    
    def _collect_single_day(self, trade_date: str) -> None:
        """
        采集单日债券历史实时数据
        
        表名: base_bond_data_{yyyyMMdd}
        数据: 1分钟K线数据（09:30-11:30, 13:00-15:00）
        """
        table_name = f"base_bond_data_{trade_date.replace('-', '')}"
        
        # 1. 检查并清理旧表
        if self.mysql_tool.check_table_exists(table_name):
            self.mysql_tool.drop_mysql_table(table_name)
        
        # 2. 获取可转债代码列表
        bond_codes = self._get_bond_codes()
        
        # 3. 连接TDX
        api = self._get_tdx_api()
        if not api:
            logger.error("TDX连接失败")
            return
        
        # 4. 采集所有转债的1分钟K线
        all_data = []
        for market, code in bond_codes:
            df = self._get_min1_bars(api, market, code, trade_date)
            if df is not None and not df.empty:
                all_data.append(df)
        
        # 5. 合并并写入MySQL
        if all_data:
            df_all = pd.concat(all_data, ignore_index=True)
            self._write_to_mysql(df_all, table_name)
            logger.info(f"{trade_date}: 写入 {len(df_all)} 条数据到 {table_name}")
    
    def _get_bond_codes(self) -> List[Tuple[int, str]]:
        """
        获取可转债代码列表
        
        Returns:
            List[(market, code)]
            market: 0=深圳, 1=上海
            code: 12xxxx(深圳) 或 11xxxx(上海)
        """
        codes = []
        api = self._get_tdx_api()
        if not api:
            return codes
        
        # 深圳 (market=0): 12开头
        count = api.get_security_count(0)
        for start in range(0, count, 1000):
            items = api.get_security_list(0, start)
            for s in items:
                if s['code'].startswith('12'):
                    codes.append((0, s['code']))
        
        # 上海 (market=1): 11开头
        count = api.get_security_count(1)
        for start in range(0, count, 1000):
            items = api.get_security_list(1, start)
            for s in items:
                if s['code'].startswith('11'):
                    codes.append((1, s['code']))
        
        return codes
    
    def _get_min1_bars(self, api, market: int, code: str, trade_date: str) -> pd.DataFrame:
        """
        获取单只转债的1分钟K线数据
        
        TDX API: get_security_bars(8, market, code, 0, 240)
        - 8: 1分钟K线
        - 240: 最大返回条数（4小时*60分钟）
        
        Returns:
            DataFrame: time, open, high, low, close, volume, amount
        """
        try:
            # 获取1分钟K线
            bars = api.get_security_bars(8, market, code, 0, 240)
            
            if not bars:
                return pd.DataFrame()
            
            # 转换为DataFrame
            rows = []
            for bar in bars:
                # TDX时间格式:YYYYMMDDHHMM
                dt_str = str(bar['datetime'])
                dt = datetime.strptime(dt_str, '%Y%m%d%H%M')
                
                # 只保留交易时间 (09:30-11:30, 13:00-15:00)
                if not self._is_trading_time(dt):
                    continue
                
                rows.append({
                    'bond_code': code,
                    'bond_name': bar.get('name', ''),
                    'time': dt.strftime('%H:%M'),
                    'datetime': dt,
                    'open': bar['open'] / 100,      # 价格除以100
                    'high': bar['high'] / 100,
                    'low': bar['low'] / 100,
                    'close': bar['close'] / 100,
                    'volume': bar['vol'],
                    'amount': bar['amount'],
                })
            
            return pd.DataFrame(rows)
        
        except Exception as e:
            logger.error(f"获取 {code} 1分钟K线失败: {e}")
            return pd.DataFrame()
    
    def _is_trading_time(self, dt: datetime) -> bool:
        """判断是否为交易时间"""
        t = dt.time()
        # 上午 09:30-11:30
        if time(9, 30) <= t <= time(11, 30):
            return True
        # 下午 13:00-15:00
        if time(13, 0) <= t <= time(15, 0):
            return True
        return False
    
    def _write_to_mysql(self, df: pd.DataFrame, table_name: str) -> None:
        """写入MySQL"""
        with self.engine.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
    
    def _get_tdx_api(self):
        """获取或创建TDX API连接（带缓存）"""
        if self.tdx_api:
            return self.tdx_api
        
        from pytdx.hq import TdxHq_API
        
        servers = [
            ('202.108.253.139', 80),
            ('123.125.108.90', 7709),
            ('218.75.126.9', 7709),
        ]
        
        api = TdxHq_API()
        for host, port in servers:
            try:
                api.connect(host, port, time_out=10)
                self.tdx_api = api
                logger.info(f"TDX连接成功: {host}:{port}")
                return api
            except:
                continue
        
        return None
```

### 3. 表结构

```sql
CREATE TABLE `base_bond_data_20260115` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `bond_code` VARCHAR(6) NOT NULL COMMENT '转债代码',
    `bond_name` VARCHAR(50) COMMENT '转债名称',
    `time` VARCHAR(5) NOT NULL COMMENT '时间 HH:MM',
    `datetime` DATETIME NOT NULL COMMENT '完整时间',
    `open` DECIMAL(10,3) COMMENT '开盘价',
    `high` DECIMAL(10,3) COMMENT '最高价',
    `low` DECIMAL(10,3) COMMENT '最低价',
    `close` DECIMAL(10,3) COMMENT '收盘价',
    `volume` BIGINT COMMENT '成交量',
    `amount` DECIMAL(15,2) COMMENT '成交额',
    INDEX `idx_code_time` (`bond_code`, `time`),
    INDEX `idx_datetime` (`datetime`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='可转债历史实时数据';
```

### 4. 使用示例

```python
from gs2026.collection.base.bond_tdx_collector import BondTDXCollector

# 创建采集器
collector = BondTDXCollector()

# 采集2024年1月数据
collector.collect('2024-01-01', '2024-01-31')

# 采集单日数据
collector.collect('2024-01-15', '2024-01-15')
```

### 5. 关键特性

| 特性 | 说明 |
|------|------|
| **交易日获取** | 从 `data_jyrl` 表获取，借鉴量化回测 |
| **TDX连接** | 连接复用，多服务器自动切换 |
| **数据精度** | 价格除以100（TDX原始值） |
| **时间过滤** | 只保留交易时间（09:30-11:30, 13:00-15:00） |
| **表命名** | `base_bond_data_{yyyyMMdd}` |
| **错误处理** | 单只转债失败不影响其他 |

### 6. 与现有代码的关系

```
借鉴 stock_daily_collection.py:
├── _get_trade_dates() - 获取交易日列表
├── collect() - 日期范围遍历
├── _collect_single_day() - 单日采集
└── MySQL写入模式

新增 TDX 特定功能:
├── _get_tdx_api() - TDX连接管理
├── _get_bond_codes() - 可转债代码获取
├── _get_min1_bars() - 1分钟K线获取
└── _is_trading_time() - 交易时间过滤
```

---

**审核状态**: 待审核
