# MySQL 入库慢 - 完整处理方案

**分析时间**: 2026-03-30 04:38  
**当前状态**: 入库依然很慢

---

## 一、核心问题汇总

| 问题 | 当前值 | 标准值 | 严重程度 |
|------|--------|--------|----------|
| **Buffer Pool** | 128MB | 1-2GB | 🔴 严重 |
| **Redo Log** | 48MB | 256MB+ | 🔴 严重 |
| **事务刷新** | 每次提交fsync | 每秒fsync | 🔴 严重 |
| **表碎片** | 263.9% | <30% | 🔴 严重 |
| **History List** | 294 | <100 | 🟡 中等 |
| **活跃事务** | 9 | <5 | 🟡 中等 |
| **单条插入** | 101条/秒 | 1000+条/秒 | 🔴 严重 |
| **批量插入** | 4360条/秒 | 10000+条/秒 | 🟡 可接受 |

---

## 二、完整处理方案

### 🔥 阶段1: 立即优化（5分钟，提升50倍）

#### 1.1 修改 MySQL 配置（无需重启部分）

```sql
-- 动态修改配置（立即生效）
SET GLOBAL innodb_flush_log_at_trx_commit = 2;
SET GLOBAL innodb_io_capacity = 2000;
SET GLOBAL innodb_io_capacity_max = 4000;
```

**效果**: 插入速度提升 10-20 倍

#### 1.2 清理表碎片（针对263%碎片率的表）

```sql
-- 清理碎片最严重的表
OPTIMIZE TABLE data_gpsj_day_20260202;
OPTIMIZE TABLE data_gpsj_day_20260203;
OPTIMIZE TABLE data_gpsj_day_20260204;
OPTIMIZE TABLE data_gpsj_day_20260205;
OPTIMIZE TABLE data_gpsj_day_20260206;
```

**注意**: 大表优化可能需要几分钟，会锁表

#### 1.3 终止剩余长事务

```sql
-- 终止超过30分钟的事务
KILL 28666;
KILL 28676;
KILL 28667;
KILL 28668;
```

---

### 🔧 阶段2: 配置优化（需重启，提升20倍）

#### 2.1 my.ini 配置修改

```ini
[mysqld]
# === Buffer Pool ===
innodb_buffer_pool_size = 2G          # 从128MB提升到2GB（最重要！）
innodb_buffer_pool_instances = 4      # 多实例减少锁竞争

# === Redo Log ===
innodb_log_file_size = 512M           # 从48MB提升到512MB
innodb_log_files_in_group = 3         # 3个日志文件

# === 刷新策略 ===
innodb_flush_log_at_trx_commit = 2    # 每秒刷新（提升写入性能）
innodb_flush_method = O_DIRECT        # 直接IO，绕过OS缓存

# === IO容量 ===
innodb_io_capacity = 2000             # 从200提升到2000
innodb_io_capacity_max = 4000
innodb_read_io_threads = 8            # 从4提升到8
innodb_write_io_threads = 8           # 从4提升到8

# === Purge优化 ===
innodb_purge_threads = 4              # 保持4个
innodb_purge_batch_size = 1000        # 批量清理

# === 插入优化 ===
innodb_autoinc_lock_mode = 2          # 交错模式，提升并发插入
innodb_change_buffering = all         # 启用所有变更缓冲
bulk_insert_buffer_size = 256M        # 批量插入缓冲区

# === 连接优化 ===
max_connections = 200                 # 适当增加
thread_cache_size = 50                # 线程缓存

# === 查询缓存（MySQL 8.0已移除，5.7可用）===
# query_cache_type = 1
# query_cache_size = 64M
```

#### 2.2 重启 MySQL

```bash
# Windows
net stop MySQL
net start MySQL

# 或
sc stop MySQL
sc start MySQL
```

---

### 💻 阶段3: 代码优化（30分钟，提升10倍）

#### 3.1 修改 baostock_collection.py

```python
# 原代码（逐条插入）
for stock_code in stock_codes:
    df = get_multiple_stocks(stock_code, start_date, end_date)
    if df is not None:
        with engine.begin() as conn:  # 每次循环都创建事务
            df.to_sql(name=table_name, con=conn, if_exists='append')

# 优化后（批量插入）
def batch_insert(dataframes, table_name, batch_size=100):
    """批量插入数据"""
    if not dataframes:
        return
    
    # 合并DataFrame
    combined = pd.concat(dataframes, ignore_index=True)
    
    # 使用单个事务批量插入
    with engine.begin() as conn:
        combined.to_sql(
            name=table_name,
            con=conn,
            if_exists='append',
            index=False,
            method='multi',      # 使用多值插入
            chunksize=1000       # 每1000条执行一次INSERT
        )

# 主循环中使用批量插入
all_data = []
for i, stock_code in enumerate(stock_codes):
    df = get_multiple_stocks(stock_code, start_date, end_date)
    if df is not None:
        all_data.append(df)
        
        # 每100只股票批量插入
        if len(all_data) >= 100:
            batch_insert(all_data, table_name)
            logger.info(f"批量插入 {len(all_data)} 只股票")
            all_data = []

# 插入剩余数据
if all_data:
    batch_insert(all_data, table_name)
```

#### 3.2 使用 LOAD DATA INFILE（最快方式）

```python
def fast_insert(dataframes, table_name):
    """使用LOAD DATA INFILE快速插入（比INSERT快10-20倍）"""
    import tempfile
    import os
    
    if not dataframes:
        return
    
    combined = pd.concat(dataframes, ignore_index=True)
    
    # 保存为CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        csv_path = f.name
        combined.to_csv(f, index=False)
    
    try:
        # 使用LOAD DATA INFILE
        with engine.begin() as conn:
            conn.execute(text(f"""
                LOAD DATA LOCAL INFILE '{csv_path}'
                INTO TABLE {table_name}
                FIELDS TERMINATED BY ','
                ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                IGNORE 1 ROWS
            """))
    finally:
        os.unlink(csv_path)
```

#### 3.3 禁用索引（大量插入时）

```python
def insert_with_disabled_indexes(dataframes, table_name):
    """插入时禁用索引，插入后重建"""
    with engine.begin() as conn:
        # 禁用索引
        conn.execute(text(f"ALTER TABLE {table_name} DISABLE KEYS"))
        
        # 批量插入
        combined = pd.concat(dataframes, ignore_index=True)
        combined.to_sql(name=table_name, con=conn, if_exists='append', index=False)
        
        # 重建索引
        conn.execute(text(f"ALTER TABLE {table_name} ENABLE KEYS"))
```

---

### 🗄️ 阶段4: 表结构优化（1小时，提升5倍）

#### 4.1 优化表结构

```sql
-- 查看当前表结构
SHOW CREATE TABLE data_gpsj_day_20260330;

-- 优化建议：
-- 1. 使用合适的数据类型
-- 2. 减少索引数量
-- 3. 使用分区表（如果数据量大）

-- 创建优化后的新表
CREATE TABLE data_gpsj_day_new (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    trade_time DATETIME,
    open DECIMAL(10,2),
    close DECIMAL(10,2),
    high DECIMAL(10,2),
    low DECIMAL(10,2),
    volume BIGINT,
    amount DECIMAL(15,2),
    change_pct DECIMAL(6,2),
    change_val DECIMAL(10,2),
    turnover_ratio DECIMAL(6,2),
    pre_close DECIMAL(10,2),
    INDEX idx_stock_date (stock_code, trade_date),
    INDEX idx_date (trade_date)
) ENGINE=InnoDB 
ROW_FORMAT=COMPRESSED  -- 压缩存储
KEY_BLOCK_SIZE=8;      -- 8KB块大小
```

#### 4.2 使用分区表（推荐大数据量）

```sql
-- 按日期范围分区
CREATE TABLE data_gpsj_day_partitioned (
    id BIGINT AUTO_INCREMENT,
    stock_code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    -- ... 其他字段
    PRIMARY KEY (id, trade_date),
    INDEX idx_stock_date (stock_code, trade_date)
) ENGINE=InnoDB
PARTITION BY RANGE (YEAR(trade_date) * 100 + MONTH(trade_date)) (
    PARTITION p202601 VALUES LESS THAN (202602),
    PARTITION p202602 VALUES LESS THAN (202603),
    PARTITION p202603 VALUES LESS THAN (202604),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

---

### 🧹 阶段5: 定期维护（持续）

#### 5.1 每日维护脚本

```python
#!/usr/bin/env python3
# daily_maintenance.py

from sqlalchemy import create_engine, text

def daily_maintenance():
    engine = create_engine(url)
    
    with engine.connect() as conn:
        # 1. 清理碎片（小表）
        conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'gs' 
              AND data_free / data_length > 0.3
              AND data_length < 104857600  -- 小于100MB的表
        """))
        
        # 2. 更新统计信息
        conn.execute(text("ANALYZE TABLE data_gpsj_day_20260330"))
        
        # 3. 检查长事务
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.innodb_trx 
            WHERE TIMESTAMPDIFF(SECOND, trx_started, NOW()) > 300
        """))
        long_trx = result.fetchone()[0]
        
        if long_trx > 0:
            print(f"警告: 发现 {long_trx} 个长时间事务")

daily_maintenance()
```

#### 5.2 每周维护

```sql
-- 每周执行一次
-- 1. 优化大表
OPTIMIZE TABLE data_gpsj_day_all19900101;

-- 2. 清理二进制日志
PURGE BINARY LOGS BEFORE DATE(NOW() - INTERVAL 7 DAY);

-- 3. 更新所有表统计信息
ANALYZE TABLE data_gpsj_day_20260330;
```

---

## 三、实施顺序建议

| 阶段 | 操作 | 预计时间 | 提升倍数 | 风险 |
|------|------|----------|----------|------|
| 1 | 动态修改配置 | 1分钟 | 10x | 无 |
| 2 | 清理碎片（小表） | 5分钟 | 2x | 低 |
| 3 | 终止长事务 | 1分钟 | 2x | 低 |
| 4 | 修改代码批量插入 | 30分钟 | 50x | 中 |
| 5 | 重启MySQL改配置 | 5分钟 | 20x | 中 |
| 6 | 优化表结构 | 60分钟 | 5x | 高 |

**推荐顺序**: 1 → 2 → 3 → 4 → 5 → 6

---

## 四、预期效果

| 指标 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 单条插入 | 101条/秒 | 5000+条/秒 | 50x |
| 批量插入 | 4360条/秒 | 50000+条/秒 | 11x |
| Baostock采集 | 83分钟 | 2分钟 | 40x |
| History List | 294 | <50 | 6x |
| 表碎片 | 263% | <10% | 26x |

---

## 五、监控指标

```python
# 监控脚本
import time

def monitor_mysql():
    while True:
        with engine.connect() as conn:
            # 检查History List
            result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
            status = result.fetchone()[2]
            for line in status.split('\n'):
                if 'History list length' in line:
                    hll = int(line.split(':')[1].strip())
                    if hll > 1000:
                        print(f"警告: History List Length = {hll}")
                    break
            
            # 检查活跃事务
            result = conn.execute(text("SELECT COUNT(*) FROM information_schema.innodb_trx"))
            trx_count = result.fetchone()[0]
            if trx_count > 10:
                print(f"警告: 活跃事务数 = {trx_count}")
        
        time.sleep(60)
```

---

**请确认从哪个阶段开始实施？**
