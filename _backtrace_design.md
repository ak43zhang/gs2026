# 股债交集回溯系统设计方案

## 需求概述

遍历当日或指定日期的时间轴，将股票上攻排行和债券上攻排行分别按条件过滤后取交集，保存到 MySQL，保持幂等性。

## 核心字段分析

### 股票字段 (STOCK_COLUMNS)
```
固定: #, code, name
可选: change_pct, price, count, window_count, main_net_amount, bond_code, bond_name, industry,
      consecutive_attacks, main_net_count, max_cumulative_main_net
```

### 债券字段 (BOND_COLUMNS)
```
固定: #, code, name
可选: change_pct, price, count, window_count, amount, industry, main_net_amount,
      min1_change_pct, min1_amount, weighted_slope_2m/5m/15m, change_1m_pct, price_acceleration,
      mkt_weighted_slope_2m/5m/15m, mkt_change_1m_pct
```

### 交集字段（共同拥有）
| 字段 | 股票 | 债券 | 说明 |
|------|------|------|------|
| code | ✅ | ✅ | 代码 |
| name | ✅ | ✅ | 名称 |
| change_pct | ✅ | ✅ | 涨跌幅 |
| price | ✅ | ✅ | 现价 |
| count | ✅ | ✅ | 累计次数 |
| window_count | ✅ | ✅ | 区间次数 |
| industry | ✅ | ✅ | 行业 |
| main_net_amount | ✅ | ✅ | 主力净额 |

### 关联字段
- 股票有 `bond_code`, `bond_name` 字段，可直接关联债券

## 数据表设计

### 表名: `backtrace_stock_bond_intersection`

```sql
CREATE TABLE backtrace_stock_bond_intersection (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 时间维度
    trade_date DATE NOT NULL COMMENT '交易日期',
    trade_time TIME NOT NULL COMMENT '交易时间',
    
    -- 股票信息
    stock_code VARCHAR(16) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(32) COMMENT '股票名称',
    stock_change_pct DECIMAL(10,4) COMMENT '股票涨跌幅%',
    stock_price DECIMAL(10,4) COMMENT '股票现价',
    stock_count INT COMMENT '股票累计次数',
    stock_window_count INT COMMENT '股票区间次数',
    stock_industry VARCHAR(32) COMMENT '股票行业',
    stock_main_net_amount DECIMAL(16,2) COMMENT '股票主力净额',
    
    -- 债券信息
    bond_code VARCHAR(16) NOT NULL COMMENT '债券代码',
    bond_name VARCHAR(32) COMMENT '债券名称',
    bond_change_pct DECIMAL(10,4) COMMENT '债券涨跌幅%',
    bond_price DECIMAL(10,4) COMMENT '债券现价',
    bond_count INT COMMENT '债券累计次数',
    bond_window_count INT COMMENT '债券区间次数',
    bond_industry VARCHAR(32) COMMENT '债券行业',
    bond_main_net_amount DECIMAL(16,2) COMMENT '债券主力净额',
    
    -- 过滤条件快照（JSON存储，用于追溯）
    filter_config JSON COMMENT '过滤条件配置快照',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 唯一索引保证幂等性
    UNIQUE KEY uk_date_time_stock_bond (trade_date, trade_time, stock_code, bond_code),
    
    -- 查询索引
    KEY idx_date_time (trade_date, trade_time),
    KEY idx_stock_code (stock_code),
    KEY idx_bond_code (bond_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股债交集回溯结果表';
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    BacktraceRunner                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ TimeAxis    │  │ StockFilter │  │ BondFilter          │ │
│  │ Iterator    │→ │ (Pipeline)  │→ │ (Pipeline)          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         ↓                              ↓                  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           IntersectionCalculator                      │ │
│  │  (按 bond_code 关联：stock.bond_code == bond.code)    │ │
│  └──────────────────────────────────────────────────────┘ │
│         ↓                                                  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           MySQLRepository (幂等写入)                 │ │
│  │  INSERT ... ON DUPLICATE KEY UPDATE                  │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 过滤条件配置

### 配置结构 (filter_config JSON)

```python
{
    "date": "20260803",           # 日期
    "time_range": {               # 时间范围
        "start": "09:30:00",
        "end": "15:00:00",
        "interval": "1min"        # 遍历间隔：1min/5min/15min/30min
    },
    "stock_filters": {            # 股票过滤条件
        "industry": "电子",        # 行业筛选
        "topn_sectors": 5,          # 前N行业
        "topn_window": 10,          # 前N区间次数
        "topn_count": 20,         # 前N累计次数
        "bond_filter": true         # 只显示有债券的
    },
    "bond_filters": {             # 债券过滤条件
        "industry": "电子",        # 行业筛选
        "topn_sectors": 5,          # 前N行业
        "topn_amount": 20,          # 前N金额
        "topn_window": 10,          # 前N区间次数
        "topn_count": 20,          # 前N累计次数
        "green_list": false         # 排除绿名单
    }
}
```

## 核心模块设计

### 1. BacktraceRunner (入口)

```python
class BacktraceRunner:
    """股债交集回溯运行器"""
    
    def __init__(self, config: BacktraceConfig):
        self.config = config
        self.time_axis = TimeAxisIterator(config.date, config.time_range)
        self.stock_filter = StockFilter(config.stock_filters)
        self.bond_filter = BondFilter(config.bond_filters)
        self.intersection_calc = IntersectionCalculator()
        self.repository = BacktraceRepository()
    
    def run(self) -> BacktraceResult:
        """执行回溯"""
        results = []
        
        for time_str in self.time_axis:
            # 获取原始数据
            stock_data = self._fetch_stock_data(time_str)
            bond_data = self._fetch_bond_data(time_str)
            
            # 应用过滤
            filtered_stocks = self.stock_filter.apply(stock_data)
            filtered_bonds = self.bond_filter.apply(bond_data)
            
            # 计算交集
            intersections = self.intersection_calc.calculate(
                filtered_stocks, filtered_bonds
            )
            
            # 构建记录
            records = self._build_records(time_str, intersections)
            results.extend(records)
        
        # 幂等写入
        return self.repository.save_batch(results)
```

### 2. TimeAxisIterator (时间轴遍历)

```python
class TimeAxisIterator:
    """时间轴迭代器"""
    
    def __init__(self, date: str, time_range: TimeRangeConfig):
        self.date = date
        self.start = datetime.strptime(time_range.start, "%H:%M:%S")
        self.end = datetime.strptime(time_range.end, "%H:%M:%S")
        self.interval = self._parse_interval(time_range.interval)
    
    def __iter__(self):
        current = self.start
        while current <= self.end:
            yield current.strftime("%H:%M:%S")
            current += self.interval
    
    def _parse_interval(self, interval: str) -> timedelta:
        """解析间隔"""
        mapping = {
            "1min": timedelta(minutes=1),
            "5min": timedelta(minutes=5),
            "15min": timedelta(minutes=15),
            "30min": timedelta(minutes=30),
        }
        return mapping.get(interval, timedelta(minutes=1))
```

### 3. StockFilter / BondFilter (过滤器)

复用现有的 Pipeline 逻辑，但改为后端实现：

```python
class StockFilter:
    """股票过滤器（后端复刻前端 Pipeline）"""
    
    def __init__(self, config: StockFilterConfig):
        self.config = config
        self.pipeline = self._build_pipeline()
    
    def _build_pipeline(self) -> List[Filter]:
        """构建过滤管道"""
        filters = []
        
        if self.config.industry:
            filters.append(IndustryFilter(self.config.industry))
        
        if self.config.topn_sectors:
            filters.append(TopNSectorsFilter(self.config.topn_sectors))
        
        if self.config.topn_window:
            filters.append(TopNWindowFilter(self.config.topn_window))
        
        if self.config.topn_count:
            filters.append(TopNCountFilter(self.config.topn_count))
        
        if self.config.bond_filter:
            filters.append(BondExistsFilter())
        
        return filters
    
    def apply(self, data: List[Dict]) -> List[Dict]:
        """应用过滤"""
        result = data
        for f in self.pipeline:
            result = f.apply(result)
        return result
```

### 4. IntersectionCalculator (交集计算)

```python
class IntersectionCalculator:
    """交集计算器"""
    
    def calculate(self, stocks: List[Dict], bonds: List[Dict]) -> List[StockBondPair]:
        """
        计算股债交集
        
        关联逻辑：stock['bond_code'] == bond['code']
        """
        # 建立债券 code -> 债券数据的映射
        bond_map = {b['code']: b for b in bonds}
        
        intersections = []
        for stock in stocks:
            bond_code = stock.get('bond_code')
            if bond_code and bond_code in bond_map:
                bond = bond_map[bond_code]
                intersections.append(StockBondPair(
                    stock=stock,
                    bond=bond
                ))
        
        return intersections
```

### 5. BacktraceRepository (幂等写入)

```python
class BacktraceRepository:
    """回溯结果仓库"""
    
    TABLE = "backtrace_stock_bond_intersection"
    
    def save_batch(self, records: List[BacktraceRecord]) -> BacktraceResult:
        """批量幂等写入"""
        if not records:
            return BacktraceResult(count=0)
        
        # 使用 INSERT ... ON DUPLICATE KEY UPDATE 实现幂等
        sql = f"""
            INSERT INTO {self.TABLE} (
                trade_date, trade_time,
                stock_code, stock_name, stock_change_pct, stock_price,
                stock_count, stock_window_count, stock_industry, stock_main_net_amount,
                bond_code, bond_name, bond_change_pct, bond_price,
                bond_count, bond_window_count, bond_industry, bond_main_net_amount,
                filter_config
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                stock_name = VALUES(stock_name),
                stock_change_pct = VALUES(stock_change_pct),
                stock_price = VALUES(stock_price),
                stock_count = VALUES(stock_count),
                stock_window_count = VALUES(stock_window_count),
                stock_industry = VALUES(stock_industry),
                stock_main_net_amount = VALUES(stock_main_net_amount),
                bond_name = VALUES(bond_name),
                bond_change_pct = VALUES(bond_change_pct),
                bond_price = VALUES(bond_price),
                bond_count = VALUES(bond_count),
                bond_window_count = VALUES(bond_window_count),
                bond_industry = VALUES(bond_industry),
                bond_main_net_amount = VALUES(bond_main_net_amount),
                filter_config = VALUES(filter_config),
                updated_at = CURRENT_TIMESTAMP
        """
        
        with self.engine.begin() as conn:
            conn.execute(text(sql), [self._to_tuple(r) for r in records])
        
        return BacktraceResult(count=len(records))
```

## API 设计

### 启动回溯任务

```http
POST /api/backtrace/run
Content-Type: application/json

{
    "date": "20260803",
    "time_range": {
        "start": "09:30:00",
        "end": "15:00:00",
        "interval": "5min"
    },
    "stock_filters": {
        "topn_sectors": 5,
        "topn_window": 10
    },
    "bond_filters": {
        "topn_amount": 20,
        "topn_window": 10
    }
}

Response:
{
    "success": true,
    "data": {
        "task_id": "bt-20260803-001",
        "total_times": 48,        // 时间点数
        "total_records": 156,     // 总记录数
        "duration_ms": 3250
    }
}
```

### 查询回溯结果

```http
GET /api/backtrace/results?date=20260803&time=10:30:00&page=1&size=50

Response:
{
    "success": true,
    "data": {
        "total": 156,
        "records": [
            {
                "trade_date": "2026-08-03",
                "trade_time": "10:30:00",
                "stock_code": "000001",
                "stock_name": "平安银行",
                "stock_change_pct": 2.5,
                "bond_code": "113001",
                "bond_name": "平安转债",
                "bond_change_pct": 1.8
            }
        ]
    }
}
```

## 文件结构

```
src/gs2026/tools/backtrace/
├── __init__.py
├── runner.py              # BacktraceRunner 入口
├── config.py              # 配置类定义
├── models.py              # 数据模型 (StockBondPair, BacktraceRecord)
├── time_axis.py           # TimeAxisIterator
├── filters/
│   ├── __init__.py
│   ├── base.py            # Filter 基类
│   ├── stock.py           # StockFilter
│   ├── bond.py            # BondFilter
│   └── pipeline.py        # 管道执行器
├── intersection.py        # IntersectionCalculator
├── repository.py          # BacktraceRepository
└── api.py                 # Flask API 路由
```

## 实施步骤

1. **创建数据库表** - 执行 DDL
2. **创建目录结构** - `src/gs2026/tools/backtrace/`
3. **实现核心模块** - 按依赖顺序：models → config → time_axis → filters → intersection → repository → runner → api
4. **注册 API 路由** - 在 dashboard2 中注册
5. **测试验证** - 单元测试 + 集成测试

## 幂等性保证

- 唯一索引：`uk_date_time_stock_bond (trade_date, trade_time, stock_code, bond_code)`
- 写入方式：`INSERT ... ON DUPLICATE KEY UPDATE`
- 重复执行同一配置，结果一致，不会重复插入

## 扩展性设计

- 新增过滤器：继承 Filter 基类，注册到 Pipeline
- 新增字段：修改表结构 + models.py + repository.py
- 新增关联方式：修改 IntersectionCalculator 的关联逻辑
