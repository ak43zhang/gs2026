# 开盘价管理与实体红绿柱计算

## 功能概述

本功能实现股票/债券开盘价的自动采集、持久化和实体红绿柱（K线实体）的精准计算。

## 核心特性

- **开盘价采集**：程序启动后前10个tick自动采集所有股票开盘价
- **冻结机制**：10个tick后开盘价冻结，后续不再更新，保证性能
- **双重持久化**：Redis（热缓存）+ MySQL（冷存储）
- **实体红绿柱**：基于真实开盘价计算，非近似

## 数据表结构

### market_open_prices（股票开盘价表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键，自增 |
| trade_date | VARCHAR(8) | 交易日期 YYYYMMDD |
| stock_code | VARCHAR(20) | 股票代码 |
| open_price | DECIMAL(10,2) | 开盘价 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### bond_open_prices（债券开盘价表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键，自增 |
| trade_date | VARCHAR(8) | 交易日期 YYYYMMDD |
| bond_code | VARCHAR(20) | 债券代码 |
| open_price | DECIMAL(10,2) | 开盘价 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 索引

- PRIMARY: id
- UNIQUE: (trade_date, stock_code/bond_code) - 防止重复
- INDEX: trade_date - 按日期查询
- INDEX: stock_code/bond_code - 按代码查询

## 核心模块

### open_price_manager.py（股票专用）

#### 主要函数

##### init_open_prices(date_str)
初始化开盘价管理器，尝试从缓存加载。

##### ensure_open_prices(df_now, time_str, date_str)
确保开盘价可用，自动处理采集/冻结模式。

##### get_open_price(code)
获取单只股票开盘价。

##### is_frozen()
检查是否已冻结。

### 采集流程（股票）

```
tick 1:   初始化开盘价（首批股票）
tick 2-10: 补全缺失股票
 tick >= 11: 冻结，不再更新
```

### 降级策略（股票）

- 程序重启时优先从 Redis 加载
- Redis 无数据时从 MySQL 加载
- 都无时进入采集模式

## 实体红绿柱计算

### 股票

使用采集的开盘价：

```python
is_body_up = (price > open_price)
is_body_down = (price < open_price)
is_body_flat = (price == open_price)
```

### 债券

直接使用 adata 返回的 `open` 字段：

```python
is_body_up = (price > open)
is_body_down = (price < open)
is_body_flat = (price == open)
```

### 与涨跌的区别

| 指标 | 计算基准 | 用途 |
|------|----------|------|
| 涨跌 | 昨日收盘价 | 判断当日盈亏 |
| 实体红绿 | 当日开盘价 | 判断K线实体颜色 |

### 场景对比

**场景：高开低走**
- 开盘 +5%，收盘 +1%
- 涨跌：+1%（涨）
- 实体：绿柱（当前 < 开盘）

**场景：低开高走**
- 开盘 -3%，收盘 +2%
- 涨跌：+2%（涨）
- 实体：红柱（当前 > 开盘）

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `open_price_manager.py` | 新增股票开盘价管理模块 |
| `monitor_stock.py` | 集成开盘价采集和实体红绿柱计算 |
| `monitor_stock.py` | 修改 `get_market_stats_v2` 使用精确 body |
| `monitor_stock.py` | 增加 `open_price`/`is_body_*` dtype |
| `monitor_bond.py` | 添加债券实体红绿柱计算 |

## 配置参数

```python
FREEZE_AFTER_TICKS = 10  # 10个tick后冻结
FORCE_SAVE_INTERVAL = 5  # 每5个tick强制保存
```

## 性能优化

- 冻结后零写入开销
- 批量保存（每批2000条）
- 异步持久化
- 内存缓存优先

## 今日实施记录

- 创建 `market_open_prices` 表
- 创建 `bond_open_prices` 表
- 填充 2026-05-15 股票开盘价（5096只）
- 填充 2026-05-15 债券开盘价（351只）
- 语法验证通过

## 待办

- [ ] 重启监控进程验证效果
- [ ] 验证实体红绿柱计算准确性
