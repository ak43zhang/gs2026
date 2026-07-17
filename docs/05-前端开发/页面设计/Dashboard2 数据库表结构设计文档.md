# Dashboard2 数据库表结构设计文档

## 文档信息

- **版本**: v1.0
- **日期**: 2026-05-13
- **模块**: 监控数据存储

---

## 一、概述

本文档详细说明 dashboard2 监控模块涉及的数据库表结构，包括：
- 实时数据表（monitor_gp_sssj）
- 排行数据表（monitor_gp_top30）
- 债券数据表（monitor_zq_sssj, monitor_zq_top30）
- 派生字段说明
- 索引设计

---

## 二、股票实时数据表

### 2.1 monitor_gp_sssj_YYYYMMDD

**表名说明**: 股票实时数据表，按日期分表

**用途**: 存储每3秒的股票实时行情和主力净额数据

#### 表结构

| 字段名 | 数据类型 | 是否为空 | 默认值 | 说明 |
|--------|----------|----------|--------|------|
| id | BIGINT UNSIGNED | NO | AUTO_INCREMENT | 主键ID |
| stock_code | VARCHAR(6) | NO | - | 股票代码（6位） |
| time | TIME | NO | - | 时间戳（HH:MM:SS） |
| change_pct | DECIMAL(10,4) | YES | NULL | 涨跌幅(%) |
| main_net_amount | DECIMAL(20,4) | YES | NULL | 单时段主力净额（元） |
| cumulative_main_net | DECIMAL(20,4) | YES | 0 | 累计主力净额（元）⭐ |
| consecutive_attacks | INT UNSIGNED | YES | 0 | 连续上攻次数 ⭐ |
| main_net_count | INT UNSIGNED | YES | 0 | 净额次数 ⭐ |
| max_cumulative_main_net | DECIMAL(20,4) | YES | 0 | 峰值净额（元）⭐ |
| created_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | 创建时间 |

#### 索引设计

```sql
-- 主键索引
PRIMARY KEY (id)

-- 唯一索引：股票代码 + 时间
UNIQUE KEY uk_stock_time (stock_code, time)

-- 普通索引：时间（用于时间范围查询）
KEY idx_time (time)

-- 普通索引：累计主力净额（用于排序）
KEY idx_cumulative_main_net (cumulative_main_net)

-- 普通索引：峰值净额（用于排序）
KEY idx_max_cumulative_main_net (max_cumulative_main_net)
```

#### 建表SQL

```sql
CREATE TABLE IF NOT EXISTS monitor_gp_sssj_YYYYMMDD (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(6) NOT NULL COMMENT '股票代码',
    time TIME NOT NULL COMMENT '时间戳',
    change_pct DECIMAL(10,4) DEFAULT NULL COMMENT '涨跌幅(%)',
    main_net_amount DECIMAL(20,4) DEFAULT NULL COMMENT '单时段主力净额（元）',
    cumulative_main_net DECIMAL(20,4) DEFAULT 0 COMMENT '累计主力净额（元）',
    consecutive_attacks INT UNSIGNED DEFAULT 0 COMMENT '连续上攻次数',
    main_net_count INT UNSIGNED DEFAULT 0 COMMENT '净额次数',
    max_cumulative_main_net DECIMAL(20,4) DEFAULT 0 COMMENT '峰值净额（元）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    UNIQUE KEY uk_stock_time (stock_code, time),
    KEY idx_time (time),
    KEY idx_cumulative_main_net (cumulative_main_net),
    KEY idx_max_cumulative_main_net (max_cumulative_main_net)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票实时数据表';
```

---

## 三、股票排行数据表

### 3.1 monitor_gp_top30_YYYYMMDD

**表名说明**: 股票排行数据表，按日期分表

**用途**: 存储每个时间点的股票上攻排行（TOP30）

#### 表结构

| 字段名 | 数据类型 | 是否为空 | 默认值 | 说明 |
|--------|----------|----------|--------|------|
| id | BIGINT UNSIGNED | NO | AUTO_INCREMENT | 主键ID |
| code | VARCHAR(6) | NO | - | 股票代码 |
| name | VARCHAR(20) | YES | NULL | 股票名称 |
| count | INT UNSIGNED | YES | 0 | 上攻次数 |
| time | TIME | NO | - | 时间戳 |
| created_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | 创建时间 |

#### 索引设计

```sql
-- 主键索引
PRIMARY KEY (id)

-- 唯一索引：股票代码 + 时间
UNIQUE KEY uk_code_time (code, time)

-- 普通索引：时间（用于时间范围查询）
KEY idx_time (time)

-- 普通索引：次数（用于排序）
KEY idx_count (count)
```

#### 建表SQL

```sql
CREATE TABLE IF NOT EXISTS monitor_gp_top30_YYYYMMDD (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(6) NOT NULL COMMENT '股票代码',
    name VARCHAR(20) DEFAULT NULL COMMENT '股票名称',
    count INT UNSIGNED DEFAULT 0 COMMENT '上攻次数',
    time TIME NOT NULL COMMENT '时间戳',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    UNIQUE KEY uk_code_time (code, time),
    KEY idx_time (time),
    KEY idx_count (count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票排行数据表';
```

---

## 四、债券实时数据表

### 4.1 monitor_zq_sssj_YYYYMMDD

**表名说明**: 债券实时数据表，按日期分表

**用途**: 存储每3秒的债券实时行情数据

#### 表结构

| 字段名 | 数据类型 | 是否为空 | 默认值 | 说明 |
|--------|----------|----------|--------|------|
| id | BIGINT UNSIGNED | NO | AUTO_INCREMENT | 主键ID |
| bond_code | VARCHAR(10) | NO | - | 债券代码 |
| time | TIME | NO | - | 时间戳 |
| change_pct | DECIMAL(10,4) | YES | NULL | 涨跌幅(%) |
| created_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | 创建时间 |

#### 索引设计

```sql
-- 主键索引
PRIMARY KEY (id)

-- 唯一索引：债券代码 + 时间
UNIQUE KEY uk_bond_time (bond_code, time)

-- 普通索引：时间
KEY idx_time (time)
```

#### 建表SQL

```sql
CREATE TABLE IF NOT EXISTS monitor_zq_sssj_YYYYMMDD (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    bond_code VARCHAR(10) NOT NULL COMMENT '债券代码',
    time TIME NOT NULL COMMENT '时间戳',
    change_pct DECIMAL(10,4) DEFAULT NULL COMMENT '涨跌幅(%)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    UNIQUE KEY uk_bond_time (bond_code, time),
    KEY idx_time (time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='债券实时数据表';
```

---

## 五、债券排行数据表

### 5.1 monitor_zq_top30_YYYYMMDD

**表名说明**: 债券排行数据表，按日期分表

**用途**: 存储每个时间点的债券上攻排行（TOP30）

#### 表结构

| 字段名 | 数据类型 | 是否为空 | 默认值 | 说明 |
|--------|----------|----------|--------|------|
| id | BIGINT UNSIGNED | NO | AUTO_INCREMENT | 主键ID |
| code | VARCHAR(10) | NO | - | 债券代码 |
| name | VARCHAR(50) | YES | NULL | 债券名称 |
| count | INT UNSIGNED | YES | 0 | 上攻次数 |
| time | TIME | NO | - | 时间戳 |
| created_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | 创建时间 |

#### 索引设计

```sql
-- 主键索引
PRIMARY KEY (id)

-- 唯一索引：债券代码 + 时间
UNIQUE KEY uk_code_time (code, time)

-- 普通索引：时间
KEY idx_time (time)
```

#### 建表SQL

```sql
CREATE TABLE IF NOT EXISTS monitor_zq_top30_YYYYMMDD (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(10) NOT NULL COMMENT '债券代码',
    name VARCHAR(50) DEFAULT NULL COMMENT '债券名称',
    count INT UNSIGNED DEFAULT 0 COMMENT '上攻次数',
    time TIME NOT NULL COMMENT '时间戳',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    UNIQUE KEY uk_code_time (code, time),
    KEY idx_time (time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='债券排行数据表';
```

---

## 六、字段关系与数据流转

### 6.1 表间关系

```
┌─────────────────────────────────────────────────────────────────┐
│                     monitor_gp_sssj_YYYYMMDD                     │
│                    （股票实时数据 - 3秒粒度）                      │
├─────────────────────────────────────────────────────────────────┤
│  stock_code + time (PK)                                         │
│  ├── change_pct (涨跌幅)                                        │
│  ├── main_net_amount (单时段净额)                                │
│  ├── cumulative_main_net (累计净额) ⭐                           │
│  ├── consecutive_attacks (连续上攻) ⭐                           │
│  ├── main_net_count (净额次数) ⭐                                │
│  └── max_cumulative_main_net (峰值净额) ⭐                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 聚合计算
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     monitor_gp_top30_YYYYMMDD                    │
│                     （股票排行 - 3秒粒度）                         │
├─────────────────────────────────────────────────────────────────┤
│  code + time (PK)                                               │
│  ├── name (股票名称)                                             │
│  └── count (上攻次数)                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 派生字段计算依赖

```
main_net_amount (当前时段)
    ↓
cumulative_main_net = 上一时段cumulative + 当前main_net
    ↓
max_cumulative_main_net = max(上一时段max, 当前cumulative)
    ↓
consecutive_attacks = 连续计数逻辑
    ↓
main_net_count = 累计计数逻辑
```

---

## 七、数据示例

### 7.1 monitor_gp_sssj_20260513 示例数据

| id | stock_code | time | change_pct | main_net_amount | cumulative_main_net | consecutive_attacks | main_net_count | max_cumulative_main_net |
|----|------------|------|------------|-----------------|---------------------|---------------------|----------------|------------------------|
| 1 | 301396 | 09:30:00 | 2.50 | 500000.00 | 500000.00 | 1 | 1 | 500000.00 |
| 2 | 301396 | 09:33:00 | 3.20 | 300000.00 | 800000.00 | 2 | 2 | 800000.00 |
| 3 | 301396 | 09:36:00 | 4.10 | 200000.00 | 1000000.00 | 3 | 3 | 1000000.00 |
| 4 | 301396 | 09:39:00 | 3.80 | -100000.00 | 900000.00 | 4 | 4 | 1000000.00 |
| 5 | 301396 | 09:42:00 | 2.50 | -300000.00 | 600000.00 | 5 | 5 | 1000000.00 |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |
| N | 301396 | 15:00:00 | -5.20 | -100000.00 | -2481000.00 | 0 | 25 | 661000.00 |

### 7.2 关键观察

**股票 301396 收盘时数据**:
- `cumulative_main_net`: -248.1万（当前累计主力资金）
- `max_cumulative_main_net`: 66.1万（当日峰值）
- `consecutive_attacks`: 0（收盘时无连续上攻）
- `main_net_count`: 25（当日有25个时段有主力净额）

**回落百分比计算**:
```
回落百分比 = (峰值 - 当前) / 峰值 × 100%
           = (66.1 - (-248.1)) / 66.1 × 100%
           = 314.1 / 66.1 × 100%
           = 475.2%
```

**注意**: 当当前值为负数时，回落百分比会超过100%，这表示资金不仅全部流出，还出现了净流出现象。

---

## 八、索引优化建议

### 8.1 现有索引

| 表名 | 索引名 | 字段 | 用途 |
|------|--------|------|------|
| monitor_gp_sssj_YYYYMMDD | uk_stock_time | stock_code, time | 唯一约束，防止重复数据 |
| monitor_gp_sssj_YYYYMMDD | idx_time | time | 时间范围查询 |
| monitor_gp_sssj_YYYYMMDD | idx_cumulative_main_net | cumulative_main_net | 按主力净额排序 |
| monitor_gp_sssj_YYYYMMDD | idx_max_cumulative_main_net | max_cumulative_main_net | 按峰值排序 |

### 8.2 建议添加的索引

```sql
-- 按连续上攻次数排序
CREATE INDEX idx_consecutive_attacks ON monitor_gp_sssj_YYYYMMDD(consecutive_attacks);

-- 按净额次数排序
CREATE INDEX idx_main_net_count ON monitor_gp_sssj_YYYYMMDD(main_net_count);

-- 复合索引：时间 + 累计净额（用于时间段内的排序查询）
CREATE INDEX idx_time_cumulative ON monitor_gp_sssj_YYYYMMDD(time, cumulative_main_net);
```

---

## 九、数据清理策略

### 9.1 自动分表

- 按日期分表：`monitor_gp_sssj_YYYYMMDD`
- 每日创建新表
- 历史数据保留策略：保留最近30天

### 9.2 数据归档

```sql
-- 归档30天前的数据到历史表
INSERT INTO monitor_gp_sssj_archive
SELECT * FROM monitor_gp_sssj_20260413
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- 删除原表
DROP TABLE monitor_gp_sssj_20260413;
```

### 9.3 Redis 数据过期

```python
# 设置Redis键过期时间为7天
redis_client.expire(f"monitor_gp_sssj_{date}:{time}", 7 * 24 * 3600)
```

---

## 十、附录

### 10.1 表命名规范

| 前缀 | 含义 | 示例 |
|------|------|------|
| monitor_gp_ | 股票监控 | monitor_gp_sssj, monitor_gp_top30 |
| monitor_zq_ | 债券监控 | monitor_zq_sssj, monitor_zq_top30 |
| monitor_hy_ | 行业监控 | monitor_hy_top30 |

### 10.2 后缀规范

| 后缀 | 含义 | 说明 |
|------|------|------|
| _sssj | 实时数据 | 每3秒的数据快照 |
| _top30 | 排行数据 | 每个时间点的TOP30 |
| _YYYYMMDD | 日期分表 | 按交易日分表 |

### 10.3 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-05-13 | 初始版本 |

---

*文档结束*