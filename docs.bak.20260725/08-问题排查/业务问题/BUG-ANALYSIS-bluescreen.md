# 蓝屏问题分析报告

## 问题描述

今天发生几次蓝屏，需要排查原因并给出解决方案。

---

## 系统环境

| 项目 | 值 |
|------|-----|
| CPU | Intel Core i5-9400F @ 2.90GHz |
| 内存 | 32 GB (约 20GB 可用) |
| 操作系统 | Windows 10 x64 (Build 19041) |
| Python | 运行中 |
| 监控程序 | monitor_stock.py |

---

## 可能原因分析

### 原因1：SQLAlchemy 连接池泄漏 ⭐⭐⭐（最可能）

**代码位置**: `monitor_stock.py` 第 62 行

```python
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()  # ← 问题：模块级连接，永不关闭！
```

**问题**:
1. `con = engine.connect()` 在模块导入时创建
2. 这个连接**永远不会被关闭**
3. 长时间运行后，连接池耗尽或连接失效
4. 可能导致内存泄漏或数据库连接异常

**影响**:
- 连接池中的连接数不断增加
- 每个连接占用内存
- 长时间运行后可能导致内存不足

---

### 原因2：DataFrame 深拷贝内存累积 ⭐⭐⭐

**代码位置**: `monitor_stock.py` 第 1263 行

```python
def save_dataframe_async(df, table_name, time_full, ...):
    # 深拷贝DataFrame（避免主线程后续修改影响后台写入）
    df_copy = df.copy()  # ← 问题：每次都要深拷贝
    
    # 提交到后台线程池
    _storage_executor.submit(_write_mysql_async, df_copy, ...)
    _storage_executor.submit(_write_redis_async, df_copy, ...)
```

**问题**:
1. 每 3 秒产生一次数据（5122 只股票）
2. 每次深拷贝 2 个 DataFrame（MySQL + Redis）
3. 每个 DataFrame 约 5122 行 × 多列
4. 估算内存占用：
   - 每行约 200 字节
   - 每个 DataFrame: 5122 × 200 = 1 MB
   - 每次提交 2 个: 2 MB
   - 每分钟 20 次: 40 MB
   - 每小时: 2.4 GB

**注意**: 深拷贝的 DataFrame 在后台线程写入完成后应该被释放，但如果线程池积压，会导致内存累积。

---

### 原因3：线程池任务积压 ⭐⭐⭐

**代码位置**: `monitor_stock.py` 第 1171 行

```python
_storage_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='storage')
```

**问题**:
1. 存储线程池只有 **2 个 worker**
2. 每 3 秒产生 2 个任务（MySQL + Redis）
3. 如果 MySQL 或 Redis 写入变慢，任务会积压
4. 积压的任务持有 DataFrame 引用，无法释放

**场景推演**:
```
时间        产生任务    完成    积压    内存占用
09:30:00    2个        2个     0       2MB
09:30:03    2个        1个     1个     4MB
09:30:06    2个        1个     2个     6MB
09:30:09    2个        0个     4个     10MB
...         ...        ...     ...     ...
10:30:00    2个        0个     200个   400MB
```

---

### 原因4：Redis 连接未正确关闭 ⭐⭐

**代码位置**: `monitor_stock.py` 第 2477 行

```python
if is_past_1500(target_dt):
    print(f"当前时间 {target_dt} 已过15:00，程序退出")
    redis_util.close_redis()
    sys.exit(0)
```

**问题**:
1. 正常退出时会关闭 Redis
2. 但**异常退出**（如蓝屏）时不会执行
3. Redis 连接可能处于半开状态
4. 重启后可能连接数过多

---

### 原因5：日志文件过大 ⭐

**问题**:
1. 日志文件 `monitor_stock.log` 持续增长
2. 长时间运行后可能占用大量磁盘空间
3. 磁盘 I/O 压力增大

---

### 原因6：SQLAlchemy 引擎连接池配置不当 ⭐⭐

**当前配置**:
```python
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
```

**问题**:
- `pool_recycle=3600`: 连接 1 小时后回收
- 但没有设置 `pool_size` 和 `max_overflow`
- 默认 `pool_size=5`, `max_overflow=10`
- 连接数可能过多

---

## 蓝屏触发条件分析

### 最可能的触发场景

**场景1：内存耗尽**
```
1. 程序运行数小时
2. 线程池任务积压
3. DataFrame 深拷贝累积
4. 内存使用持续增长
5. 系统内存不足
6. Windows 触发蓝屏保护
```

**场景2：数据库连接风暴**
```
1. 模块级连接 `con` 长期不关闭
2. 每次 `save_rank_to_mysql` 使用 `con.execute()`
3. 连接池中的连接不断增加
4. 数据库服务器拒绝连接
5. 程序异常，可能导致系统不稳定
```

---

## 解决方案

### 方案1：修复 SQLAlchemy 连接泄漏 ⭐⭐⭐（紧急）

**修改** `monitor_stock.py`:

```python
# 修改前（第 62 行）
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()

# 修改后
engine = create_engine(
    url, 
    pool_recycle=3600, 
    pool_pre_ping=True,
    pool_size=5,        # 连接池大小
    max_overflow=0,     # 不允许超出连接池
    pool_timeout=30     # 获取连接超时时间
)
# 删除：con = engine.connect()

# 使用时临时获取连接
def save_rank_to_mysql(rank_df, rank_name, date_str):
    """保存排行榜到 MySQL（修复连接泄漏）"""
    if rank_df is None or rank_df.empty:
        return
    
    try:
        from sqlalchemy import text
        
        table_name = f"rank_{rank_name}"
        
        # 【修复】使用 engine.begin() 上下文管理器
        with engine.begin() as conn:
            # 检查表是否存在
            check_sql = text(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = DATABASE() AND table_name = '{table_name}'
            """)
            result = conn.execute(check_sql)
            table_exists = result.scalar() > 0
            
            if not table_exists:
                logger.info(f"表 {table_name} 不存在，自动创建...")
                create_sql = text(f"""
                    CREATE TABLE {table_name} (
                        code VARCHAR(20) NOT NULL,
                        name VARCHAR(100),
                        count INT,
                        date VARCHAR(8) NOT NULL,
                        PRIMARY KEY (code, date)
                    )
                """)
                conn.execute(create_sql)
            
            # 先删除旧数据
            delete_sql = text(f"DELETE FROM {table_name} WHERE date = '{date_str}'")
            conn.execute(delete_sql)
            
            # 插入新数据
            rank_df.to_sql(table_name, con=conn, if_exists='append', index=False)
            
        logger.info(f"已保存 {rank_name} 排行榜，日期: {date_str}，共 {len(rank_df)} 条")
    except Exception as e:
        logger.error(f"保存排行榜失败: {e}")
```

---

### 方案2：优化 DataFrame 深拷贝 ⭐⭐⭐

**修改** `save_dataframe_async`:

```python
# 修改前
_storage_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='storage')

# 修改后
_storage_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='storage')  # 增加worker

# 添加任务队列大小限制
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue

# 使用有界队列
_storage_queue = queue.Queue(maxsize=20)  # 最多积压20个任务

def save_dataframe_async(df, table_name, time_full, expire_seconds, use_compression=False):
    """
    异步存储DataFrame（优化内存使用）
    """
    # 【优化】只深拷贝必要列，而不是整个DataFrame
    essential_cols = ['stock_code', 'price', 'volume', 'amount', 'change_pct',
                      'main_net_amount', 'cumulative_main_net', 'main_net_count', 
                      'max_cumulative_main_net', 'consecutive_attacks']
    
    # 过滤存在的列
    cols_to_copy = [col for col in essential_cols if col in df.columns]
    df_copy = df[cols_to_copy].copy()  # 只拷贝必要列
    
    # 检查队列是否已满
    if _storage_queue.qsize() >= 20:
        logger.warning(f"[{time_full}] 存储队列已满，丢弃旧任务")
        try:
            _storage_queue.get_nowait()  # 丢弃最旧的任务
        except queue.Empty:
            pass
    
    # 提交任务
    future_mysql = _storage_executor.submit(_write_mysql_async, df_copy, table_name, dtype_map)
    future_redis = _storage_executor.submit(_write_redis_async, df_copy, table_name, time_full,
                                              expire_seconds, use_compression)
    
    # 记录任务
    _storage_queue.put((time_full, future_mysql, future_redis))
    
    logger.info(f"[异步存储] 已提交: {table_name}:{time_full}，{len(df)}条")
```

---

### 方案3：添加内存监控和自动清理 ⭐⭐

```python
import psutil
import gc

def check_memory_usage():
    """检查内存使用情况，必要时触发清理"""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_percent = psutil.virtual_memory().percent
    
    logger.info(f"内存使用: {mem_info.rss / 1024 / 1024:.1f} MB, 系统内存使用率: {mem_percent}%")
    
    # 如果内存使用率超过 80%，触发清理
    if mem_percent > 80:
        logger.warning("内存使用率过高，触发垃圾回收")
        gc.collect()
        
    # 如果进程内存超过 2GB，警告
    if mem_info.rss > 2 * 1024 * 1024 * 1024:  # 2GB
        logger.warning(f"进程内存使用过高: {mem_info.rss / 1024 / 1024:.1f} MB")

# 在主循环中定期调用
while True:
    # ... 原有逻辑 ...
    
    # 每 60 秒检查一次内存
    if int(time.time()) % 60 == 0:
        check_memory_usage()
```

---

### 方案4：优化 SQLAlchemy 连接池配置 ⭐⭐

```python
# 修改前
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 修改后
engine = create_engine(
    url,
    pool_size=3,           # 基础连接数
    max_overflow=2,        # 最大溢出连接数
    pool_recycle=1800,     # 30分钟回收（缩短）
    pool_pre_ping=True,    # 使用前检查连接
    pool_timeout=10,       # 获取连接超时10秒
    echo=False             # 关闭SQL日志
)
```

---

### 方案5：添加日志轮转 ⭐

```python
# 修改 log_util.py
from logging.handlers import RotatingFileHandler

def setup_logger(name):
    logger = logging.getLogger(name)
    
    # 使用轮转日志处理器
    handler = RotatingFileHandler(
        'logs/monitor_stock.log',
        maxBytes=100 * 1024 * 1024,  # 100MB
        backupCount=5                # 保留5个备份
    )
    
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger
```

---

## 推荐实施顺序

| 优先级 | 方案 | 影响 | 实施难度 |
|--------|------|------|----------|
| P0 | 修复 SQLAlchemy 连接泄漏 | 高 | 中 |
| P1 | 优化 DataFrame 深拷贝 | 高 | 中 |
| P2 | 优化连接池配置 | 中 | 低 |
| P3 | 添加内存监控 | 中 | 低 |
| P4 | 日志轮转 | 低 | 低 |

---

## 验证方案

### 验证1：内存使用监控

```python
# 添加监控代码
import psutil
import time

start_time = time.time()
while True:
    process = psutil.Process()
    mem_mb = process.memory_info().rss / 1024 / 1024
    print(f"运行时间: {time.time() - start_time:.0f}s, 内存使用: {mem_mb:.1f} MB")
    time.sleep(60)
```

### 验证2：数据库连接数

```sql
-- MySQL 查看连接数
SHOW STATUS LIKE 'Threads_connected';
SHOW PROCESSLIST;
```

### 验证3：线程池任务积压

```python
# 添加监控
print(f"存储队列大小: {_storage_queue.qsize()}")
print(f"线程池活跃任务: {_storage_executor._work_queue.qsize()}")
```

---

## 总结

**最可能的原因**: SQLAlchemy 模块级连接泄漏 + DataFrame 深拷贝内存累积

**紧急修复**:
1. 删除 `con = engine.connect()`，改为临时连接
2. 增加存储线程池 worker 数
3. 只深拷贝必要列

**预期效果**:
- 内存使用稳定在 500MB-1GB
- 无连接泄漏
- 无任务积压

---

*分析报告完成*
