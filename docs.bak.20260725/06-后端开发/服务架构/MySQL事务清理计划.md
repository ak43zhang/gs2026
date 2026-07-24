# MySQL 未清理事务清理方案

**分析时间**: 2026-03-30 04:35  
**History List Length**: 607

---

## 一、问题诊断

### 1.1 发现的问题

| PID | 事务状态 | 运行时间 | 问题 |
|-----|----------|----------|------|
| 28327 | RUNNING | 6865秒 (1.9小时) | ⚠️ 长时间事务 |
| 28330 | RUNNING | 6863秒 (1.9小时) | ⚠️ 长时间事务 |
| 28336 | RUNNING | 6862秒 (1.9小时) | ⚠️ 长时间事务 |
| 28333 | RUNNING | 6862秒 (1.9小时) | ⚠️ 长时间事务 |
| 28338 | RUNNING | 6852秒 (1.9小时) | ⚠️ 长时间事务 |
| 28666 | RUNNING | 2482秒 (41分钟) | ⚠️ 长时间事务 |
| 28676 | RUNNING | 2482秒 (41分钟) | ⚠️ 长时间事务 |
| 28667 | RUNNING | 2424秒 (40分钟) | ⚠️ 长时间事务 |
| 28668 | RUNNING | 1703秒 (28分钟) | ⚠️ 长时间事务 |
| 28793 | RUNNING | 709秒 (12分钟) | ⚠️ 长时间事务 |
| 28788 | RUNNING | 708秒 (12分钟) | ⚠️ 长时间事务 |
| 28772 | RUNNING | 707秒 (12分钟) | ⚠️ 长时间事务 |
| 28758 | RUNNING | 706秒 (12分钟) | ⚠️ 长时间事务 |

**共 13 个长时间运行的事务**

### 1.2 影响

1. **History List Length 增加**: 607个未清理版本
2. **查询变慢**: 需要扫描更多历史版本
3. **插入变慢**: 需要维护更多版本链
4. **内存占用**: Undo 日志占用内存

---

## 二、清理方案

### 方案1: 终止长时间事务（立即见效）

**适用**: 确定不再需要的事务

```sql
-- 终止超过1小时的事务
KILL 28327;
KILL 28330;
KILL 28336;
KILL 28333;
KILL 28338;
KILL 28666;
KILL 28676;
KILL 28667;
KILL 28668;
```

**风险**: 
- 事务回滚可能需要时间
- 如果是重要操作，数据会丢失

---

### 方案2: 优化长事务的 SQL（推荐）

**适用**: 需要保留但优化性能

#### 2.1 分批提交
```python
# 原代码（大事务）
for stock in all_stocks:
    insert_data(stock)
# 最后统一 commit  ❌

# 优化后（小事务）
batch = []
for i, stock in enumerate(all_stocks):
    batch.append(stock)
    if len(batch) >= 100:
        insert_batch(batch)
        commit()  # 每100条提交一次 ✅
        batch = []
```

#### 2.2 使用 READ COMMITTED 隔离级别
```sql
-- 降低隔离级别，减少版本保留
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

---

### 方案3: 调整 Purge 配置（长期优化）

**适用**: 系统级优化

```ini
[mysqld]
# 增加 Purge 线程数
innodb_purge_threads = 4

# 加快 Purge 速度
innodb_purge_batch_size = 1000

# 限制 History List 长度（MySQL 8.0+）
innodb_max_undo_log_size = 1G
```

---

### 方案4: 清理 Undo 日志（谨慎）

**适用**: Undo 表空间过大

```sql
-- 查看 Undo 表空间
SELECT 
    tablespace_name,
    file_name,
    ROUND(total_extents * 65536 / 1024/1024, 2) as size_mb
FROM information_schema.files
WHERE file_type = 'UNDO LOG';

-- MySQL 8.0: 创建新的 Undo 表空间，删除旧的
CREATE UNDO TABLESPACE undo_002 ADD DATAFILE 'undo_002.ibu';
ALTER UNDO TABLESPACE undo_002 SET ACTIVE;
ALTER UNDO TABLESPACE innodb_undo_001 SET INACTIVE;
DROP UNDO TABLESPACE innodb_undo_001;
```

---

## 三、推荐实施方案

### 阶段1: 立即清理（5分钟）

1. **确认事务内容**
```sql
-- 查看事务执行的 SQL
SELECT 
    t.trx_id,
    t.trx_mysql_thread_id,
    p.INFO as sql_text
FROM information_schema.innodb_trx t
JOIN information_schema.PROCESSLIST p ON t.trx_mysql_thread_id = p.ID
WHERE t.trx_mysql_thread_id IN (28327, 28330, 28336, 28333, 28338, 28666, 28676, 28667, 28668)
ORDER BY t.trx_started;
```

2. **终止确定不需要的事务**
```sql
-- 终止超过2小时的事务
KILL 28327;
KILL 28330;
KILL 28336;
KILL 28333;
KILL 28338;
```

### 阶段2: 代码优化（30分钟）

1. **修改 baostock_collection.py**
   - 每100条数据 commit 一次
   - 使用 `READ COMMITTED` 隔离级别

2. **修改其他采集脚本**
   - 同样采用分批提交策略

### 阶段3: 配置优化（需重启，10分钟）

```ini
[mysqld]
# 优化 Purge
innodb_purge_threads = 4
innodb_purge_batch_size = 1000

# 优化 Buffer Pool
innodb_buffer_pool_size = 1G

# 优化日志
innodb_log_file_size = 256M
innodb_flush_log_at_trx_commit = 2
```

---

## 四、预防措施

### 4.1 监控脚本
```python
# 定期监控长时间事务
alert_threshold = 300  # 5分钟

# 如果 History List Length > 1000，发送告警
```

### 4.2 代码规范
1. 大事务必须分批提交
2. 查询操作使用 `READ COMMITTED`
3. 及时关闭不用的连接

### 4.3 定期维护
```sql
-- 每周执行一次
OPTIMIZE TABLE data_gpsj_day_xxxx;
```

---

## 五、预期效果

| 优化项 | 当前值 | 优化后 | 效果 |
|--------|--------|--------|------|
| History List Length | 607 | < 100 | 查询快3-5倍 |
| 事务执行时间 | 6865秒 | < 60秒 | 插入快10倍 |
| Undo 空间 | 大 | 小 | 内存节省 |

---

**建议**: 先执行阶段1终止长时间事务，观察效果后再执行后续阶段。
