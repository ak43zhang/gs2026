# 监控代码位置设计方案

## 概述

为预防蓝屏问题，需要在三个关键位置添加监控代码，实时检测：
1. **内存使用**
2. **线程池任务积压**
3. **数据库连接数**

---

## 监控位置1：主循环入口（每轮迭代监控）

### 位置

**文件**: `src/gs2026/monitor/monitor_stock.py`
**函数**: `run_monitor_loop_synced()`
**位置**: 每次 `process_func(target_dt)` 调用前后

### 代码位置（第 2507 行附近）

```python
def run_monitor_loop_synced(process_func, interval=INTERVAL):
    """
    同步监控主循环（优化版）
    """
    last_date = None
    last_memory_check = 0  # 【新增】上次内存检查时间

    while True:
        # ... 原有代码 ...
        
        # 【监控位置1】每轮迭代开始监控
        loop_start_time = time.time()
        
        # 执行主处理函数
        process_func(target_dt)
        
        # 【监控位置1】每轮迭代结束监控
        loop_end_time = time.time()
        loop_duration = loop_end_time - loop_start_time
        
        # 每60秒执行一次全面监控
        if loop_end_time - last_memory_check >= 60:
            perform_health_check(target_dt)  # 【新增】健康检查
            last_memory_check = loop_end_time
        
        # 如果单轮耗时超过5秒，警告
        if loop_duration > 5:
            logger.warning(f"[{target_dt.strftime('%H:%M:%S')}] 单轮处理耗时过长: {loop_duration:.2f}s")
```

### 监控内容

| 指标 | 阈值 | 动作 |
|------|------|------|
| 单轮处理时间 | > 5秒 | 警告日志 |
| 内存使用率 | > 80% | 触发垃圾回收 |
| 进程内存 | > 2GB | 严重警告 |
| 系统内存 | > 90% | 建议重启 |

---

## 监控位置2：数据存储前（存储队列监控）

### 位置

**文件**: `src/gs2026/monitor/monitor_stock.py`
**函数**: `save_dataframe_async()`
**位置**: 提交任务到线程池之前

### 代码位置（第 1256 行附近）

```python
def save_dataframe_async(df: pd.DataFrame, table_name: str, time_full: str,
                         expire_seconds: int, use_compression: bool = False) -> None:
    """
    异步存储DataFrame到MySQL和Redis（非阻塞）
    """
    # 【监控位置2】存储前监控
    
    # 1. 检查线程池队列深度
    queue_size = _storage_executor._work_queue.qsize()  # 【新增】
    if queue_size > 10:  # 阈值
        logger.warning(f"[{time_full}] 存储线程池队列积压: {queue_size} 个任务")
    
    # 2. 检查内存使用
    process = psutil.Process()
    mem_mb = process.memory_info().rss / 1024 / 1024
    if mem_mb > 1024:  # 1GB
        logger.warning(f"[{time_full}] 进程内存使用过高: {mem_mb:.1f} MB")
    
    # 3. 检查DataFrame大小
    df_size_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
    if df_size_mb > 50:  # 50MB
        logger.warning(f"[{time_full}] DataFrame过大: {df_size_mb:.1f} MB，行数: {len(df)}")
    
    # 原有代码...
    dtype_map = _get_dtype_map(df, table_name)
    df_copy = df.copy()
    
    # 【监控位置2】提交任务后监控
    _storage_executor.submit(_write_mysql_async, df_copy, table_name, dtype_map)
    _storage_executor.submit(_write_redis_async, df_copy, table_name, time_full,
                             expire_seconds, use_compression)
    
    # 记录当前积压情况
    logger.info(f"[异步存储] 已提交: {table_name}:{time_full}，{len(df)}条，"
                f"队列积压: {queue_size} 个任务，内存: {mem_mb:.1f}MB")
```

### 监控内容

| 指标 | 阈值 | 动作 |
|------|------|------|
| 线程池队列深度 | > 10 | 警告日志 |
| 进程内存 | > 1GB | 警告日志 |
| DataFrame大小 | > 50MB | 警告日志 |
| 任务提交延迟 | > 1秒 | 警告日志 |

---

## 监控位置3：数据库操作前（连接监控）

### 位置

**文件**: `src/gs2026/monitor/monitor_stock.py`
**函数**: `_write_mysql_async()`
**位置**: 执行 SQL 操作之前

### 代码位置（第 1231 行附近）

```python
def _write_mysql_async(df: pd.DataFrame, table_name: str, dtype_map: dict) -> None:
    """
    MySQL写入（在后台线程执行）
    """
    # 【监控位置3】数据库操作前监控
    
    start_time = time.time()
    
    try:
        # 1. 检查连接池状态
        pool_status = {
            'size': engine.pool.size(),           # 当前连接数
            'checked_in': engine.pool.checkedin(),  # 可用连接
            'checked_out': engine.pool.checkedout(), # 使用中连接
            'overflow': engine.pool.overflow(),      # 溢出连接
        }
        
        if pool_status['checked_out'] > 5:  # 阈值
            logger.warning(f"[MySQL] 连接池使用中连接过多: {pool_status}")
        
        # 2. 记录写入开始
        logger.info(f"[MySQL] 开始写入 {table_name}，{len(df)}条，连接池: {pool_status}")
        
        # 原有代码...
        with engine.begin() as conn:
            df.to_sql(table_name, con=conn, if_exists='append',
                      index=False, method='multi', dtype=dtype_map)
        
        # 【监控位置3】数据库操作后监控
        duration = time.time() - start_time
        
        if duration > 3:  # 3秒
            logger.warning(f"[MySQL] 写入耗时过长: {duration:.2f}s，表: {table_name}")
        else:
            logger.info(f"[MySQL] 写入完成: {table_name}，{len(df)}条，耗时: {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"[MySQL] 写入失败: {table_name}, {e}")
        raise
```

### 监控内容

| 指标 | 阈值 | 动作 |
|------|------|------|
| 连接池使用中连接 | > 5 | 警告日志 |
| 连接池溢出 | > 0 | 警告日志 |
| SQL执行时间 | > 3秒 | 警告日志 |
| SQL错误 | 任何 | 错误日志 |

---

## 监控函数实现

### 健康检查函数

```python
# 【新增】在 monitor_stock.py 中添加

import psutil
import gc
from datetime import datetime

# 监控状态缓存
_monitor_stats = {
    'last_check': 0,
    'memory_samples': [],  # 内存使用历史
    'queue_samples': [],   # 队列深度历史
    'error_count': 0,      # 错误计数
}

def perform_health_check(target_dt: datetime):
    """
    执行全面健康检查
    
    Args:
        target_dt: 当前时间
    """
    try:
        now = time.time()
        
        # 1. 系统内存
        mem = psutil.virtual_memory()
        system_memory_percent = mem.percent
        
        # 2. 进程内存
        process = psutil.Process()
        process_memory_mb = process.memory_info().rss / 1024 / 1024
        
        # 3. 线程池队列
        fetch_queue = _fetch_executor._work_queue.qsize() if hasattr(_fetch_executor, '_work_queue') else 0
        storage_queue = _storage_executor._work_queue.qsize() if hasattr(_storage_executor, '_work_queue') else 0
        
        # 4. 连接池状态
        pool_status = {
            'size': engine.pool.size() if hasattr(engine, 'pool') else 0,
            'checked_in': engine.pool.checkedin() if hasattr(engine, 'pool') else 0,
            'checked_out': engine.pool.checkedout() if hasattr(engine, 'pool') else 0,
        }
        
        # 记录样本
        _monitor_stats['memory_samples'].append(process_memory_mb)
        _monitor_stats['queue_samples'].append(storage_queue)
        if len(_monitor_stats['memory_samples']) > 60:  # 保留60个样本
            _monitor_stats['memory_samples'].pop(0)
        if len(_monitor_stats['queue_samples']) > 60:
            _monitor_stats['queue_samples'].pop(0)
        
        # 计算趋势
        memory_trend = "stable"
        if len(_monitor_stats['memory_samples']) >= 10:
            recent_avg = sum(_monitor_stats['memory_samples'][-10:]) / 10
            older_avg = sum(_monitor_stats['memory_samples'][:10]) / 10
            if recent_avg > older_avg * 1.2:  # 增长20%
                memory_trend = "increasing"
            elif recent_avg < older_avg * 0.8:
                memory_trend = "decreasing"
        
        # 输出健康报告
        logger.info(
            f"[健康检查] {target_dt.strftime('%H:%M:%S')} | "
            f"系统内存: {system_memory_percent}% | "
            f"进程内存: {process_memory_mb:.1f}MB ({memory_trend}) | "
            f"存储队列: {storage_queue} | "
            f"获取队列: {fetch_queue} | "
            f"连接池: {pool_status['checked_out']}/{pool_status['size']}"
        )
        
        # 触发垃圾回收（如果内存使用率高）
        if system_memory_percent > 80 or process_memory_mb > 1500:
            logger.warning(f"[健康检查] 内存使用率高，触发垃圾回收")
            gc.collect()
            
            # 再次检查
            process = psutil.Process()
            new_mem_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"[健康检查] 垃圾回收后内存: {new_mem_mb:.1f}MB")
        
        # 严重警告
        if system_memory_percent > 90:
            logger.error(f"[健康检查] 系统内存严重不足: {system_memory_percent}%")
        if process_memory_mb > 2000:
            logger.error(f"[健康检查] 进程内存使用过高: {process_memory_mb:.1f}MB")
        if storage_queue > 20:
            logger.error(f"[健康检查] 存储队列严重积压: {storage_queue}")
        
        _monitor_stats['last_check'] = now
        
    except Exception as e:
        logger.error(f"[健康检查] 执行失败: {e}")
```

---

## 监控日志示例

### 正常情况

```
[健康检查] 10:30:00 | 系统内存: 45% | 进程内存: 512.3MB (stable) | 存储队列: 2 | 获取队列: 0 | 连接池: 2/5
[异步存储] 已提交: monitor_gp_sssj_20260513:10:30:00，5122条，队列积压: 2 个任务，内存: 512.3MB
[MySQL] 写入完成: monitor_gp_sssj_20260513，5122条，耗时: 0.85s
```

### 警告情况

```
[健康检查] 10:30:00 | 系统内存: 82% | 进程内存: 1536.7MB (increasing) | 存储队列: 12 | 获取队列: 0 | 连接池: 6/5
[健康检查] 内存使用率高，触发垃圾回收
[健康检查] 垃圾回收后内存: 1450.2MB
[警告] [10:30:00] 存储线程池队列积压: 12 个任务
[警告] [MySQL] 写入耗时过长: 5.23s，表: monitor_gp_sssj_20260513
```

### 严重情况

```
[健康检查] 10:30:00 | 系统内存: 92% | 进程内存: 2048.5MB (increasing) | 存储队列: 25 | 获取队列: 3 | 连接池: 8/5
[错误] [健康检查] 系统内存严重不足: 92%
[错误] [健康检查] 进程内存使用过高: 2048.5MB
[错误] [健康检查] 存储队列严重积压: 25
```

---

## 实施建议

### 实施顺序

1. **位置2**（存储监控）- 最先实施，能立即发现 DataFrame 和队列问题
2. **位置3**（数据库监控）- 其次实施，监控连接池状态
3. **位置1**（主循环监控）- 最后实施，全面健康检查

### 依赖安装

```bash
pip install psutil  # 如果未安装
```

### 配置调整

```python
# 在 monitor_stock.py 顶部添加
import psutil
import gc

# 调整阈值（根据实际运行情况）
MEMORY_WARNING_THRESHOLD = 80      # 系统内存警告阈值
PROCESS_MEMORY_WARNING = 1024      # 进程内存警告阈值（MB）
PROCESS_MEMORY_CRITICAL = 2048     # 进程内存严重阈值（MB）
QUEUE_WARNING_THRESHOLD = 10       # 队列积压警告阈值
QUEUE_CRITICAL_THRESHOLD = 20      # 队列积压严重阈值
SQL_TIMEOUT_WARNING = 3              # SQL执行时间警告阈值（秒）
```

---

## 总结

| 监控位置 | 文件 | 函数 | 监控重点 | 实施优先级 |
|----------|------|------|----------|------------|
| 位置1 | monitor_stock.py | run_monitor_loop_synced() | 内存趋势、系统健康 | P2 |
| 位置2 | monitor_stock.py | save_dataframe_async() | DataFrame大小、队列深度 | P0 |
| 位置3 | monitor_stock.py | _write_mysql_async() | 连接池状态、SQL耗时 | P1 |

---

*设计方案完成*
