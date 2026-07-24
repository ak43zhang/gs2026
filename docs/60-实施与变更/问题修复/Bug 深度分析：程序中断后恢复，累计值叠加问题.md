# Bug 深度分析：程序中断后恢复，累计值叠加问题

## 问题描述

**场景**:
- 09:30:00 - 程序正常运行，累计主力资金: 1000万
- 09:30:15 - 程序中断（崩溃/重启）
- 09:30:30 - 程序恢复运行

**问题**: 09:30:30 恢复后，能否正确叠加 09:30:00 的 1000万？

---

## 当前实现分析

### 1. 数据获取逻辑

**代码**: `monitor_stock.py` 第 1995-2010 行

```python
# 找上一个有数据的时间点（非15秒周期）
prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
if prev_time:
    df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
```

**实现**: `redis_util.py` 第 938-1000 行

```python
def get_prev_timestamp_with_data(table_name: str, current_time: str) -> Optional[str]:
    # 方法1: Redis时间戳列表
    redis_client = _get_redis_client()
    if redis_client:
        try:
            ts_key = f"{table_name}:timestamps"
            all_ts = redis_client.lrange(ts_key, 0, -1)
            # ...
    
    # 方法2: MySQL查询（备用）
    if not prev_time:
        try:
            query = text(f"""
                SELECT MAX(time) as prev_time
                FROM {table_name}
                WHERE time < :current_time
                LIMIT 1
            """)
```

### 2. 数据加载逻辑

**代码**: `redis_util.py` 第 1000-1030 行

```python
def load_dataframe_by_time(table_name: str, time_str: str, ...) -> Optional[pd.DataFrame]:
    # 1. 优先Redis
    redis_key = f"{table_name}:{time_str}"
    df = load_dataframe_by_key(redis_key, ...)
    
    if df is not None and not df.empty:
        return df
    
    # 2. MySQL回退
    try:
        query = text(f"SELECT * FROM {table_name} WHERE time = :time_str")
        df = pd.read_sql(query, conn, params={"time_str": time_str})
        return df if not df.empty else None
```

---

## 场景推演

### 场景1：程序中断 15 秒（09:30:15 - 09:30:30）

**数据状态**:
```
时间        Redis                   MySQL
09:30:00    ✓ 有数据（已写入）       ✓ 有数据（异步写入）
09:30:03    ✓ 有数据                 ✓ 有数据
09:30:06    ✓ 有数据                 ✓ 有数据
09:30:09    ✓ 有数据                 ✓ 有数据
09:30:12    ✓ 有数据                 ✓ 有数据
09:30:15    ✗ 程序中断，无数据       ✗ 无数据
09:30:18    ✗ 程序中断，无数据       ✗ 无数据
09:30:21    ✗ 程序中断，无数据       ✗ 无数据
09:30:24    ✗ 程序中断，无数据       ✗ 无数据
09:30:27    ✗ 程序中断，无数据       ✗ 无数据
09:30:30    ✓ 程序恢复，开始计算     ✓ 开始写入
```

**恢复时逻辑**:
```python
# 09:30:30 恢复运行
prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "09:30:30")
# 返回值: "09:30:12"（Redis 或 MySQL 中最后一条数据）

df_prev_main = load_dataframe_by_time("monitor_gp_sssj_20260513", "09:30:12")
# 返回值: DataFrame（包含 09:30:12 的累计值）

# 计算新累计值
df_now['cumulative_main_net'] = df_prev_main['cumulative_main_net'] + df_now['main_net_amount']
# 结果: 正确叠加 ✓
```

**结论**: ✓ **可以正确叠加**

---

### 场景2：程序中断 1 小时（09:30 - 10:30）

**数据状态**:
```
时间        Redis                   MySQL
09:30:00    ✓ 有数据                ✓ 有数据
...         ✓ 有数据                ✓ 有数据
10:00:00    ✓ 有数据                ✓ 有数据（已过期？）
10:30:00    ✗ 程序恢复              ✗ 中间数据可能已过期
```

**问题**: Redis 数据有过期时间（默认 7 天），1 小时内不会过期。

**恢复时逻辑**:
```python
prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "10:30:00")
# 返回值: "10:00:00"（Redis 中最后一条数据）

df_prev_main = load_dataframe_by_time(..., "10:00:00")
# 返回值: DataFrame（包含 10:00:00 的累计值）

# 计算新累计值
df_now['cumulative_main_net'] = 10:00 的累计值 + 10:30 的当前值
# 结果: 正确叠加 ✓
```

**结论**: ✓ **可以正确叠加**

---

### 场景3：Redis 数据丢失，MySQL 有数据

**数据状态**:
```
时间        Redis                   MySQL
09:30:00    ✗ 数据丢失（重启清空）   ✓ 有数据
09:30:03    ✗ 数据丢失              ✓ 有数据
...         ✗ 数据丢失              ✓ 有数据
09:30:30    ✗ 程序恢复              ✓ 有数据
```

**恢复时逻辑**:
```python
prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "09:30:30")
# 方法1: Redis 时间戳列表 - 失败（无数据）
# 方法2: MySQL 查询 - 成功
# 返回值: "09:30:27"（MySQL 中最后一条数据）

df_prev_main = load_dataframe_by_time("monitor_gp_sssj_20260513", "09:30:27")
# 方法1: Redis - 失败（无数据）
# 方法2: MySQL - 成功
# 返回值: DataFrame（包含 09:30:27 的累计值）

# 计算新累计值
df_now['cumulative_main_net'] = 09:30:27 的累计值 + 09:30:30 的当前值
# 结果: 正确叠加 ✓
```

**结论**: ✓ **可以正确叠加**（MySQL 备用机制生效）

---

### 场景4：Redis 和 MySQL 都丢失部分数据

**数据状态**:
```
时间        Redis                   MySQL
09:30:00    ✓ 有数据                ✓ 有数据
09:30:03    ✓ 有数据                ✓ 有数据
09:30:06    ✓ 有数据                ✗ 异步写入失败
09:30:09    ✓ 有数据                ✗ 异步写入失败
09:30:12    ✗ 数据过期              ✗ 写入失败
09:30:15    ✗ 程序中断              ✗ 程序中断
09:30:30    ✗ 程序恢复              ✗ 程序恢复
```

**恢复时逻辑**:
```python
prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "09:30:30")
# 方法1: Redis - 找到 "09:30:09"
# 方法2: MySQL - 找到 "09:30:03"
# 返回值: "09:30:09"（取最新的）

df_prev_main = load_dataframe_by_time("monitor_gp_sssj_20260513", "09:30:09")
# 方法1: Redis - 失败（数据已过期）
# 方法2: MySQL - 失败（写入失败）
# 返回值: None

# 进入 else 分支
df_now['cumulative_main_net'] = 0.0  # ← 重置为0！
```

**结论**: ✗ **无法叠加**，累计值从 0 开始

---

### 场景5：程序中断跨越交易日

**数据状态**:
```
日期        时间        累计值
2026-05-12  15:00:00    5000万（收盘）
2026-05-13  09:30:00    程序恢复
```

**恢复时逻辑**:
```python
sssj_table = "monitor_gp_sssj_20260513"  # 新日期

prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "09:30:00")
# 返回值: None（新日期，无历史数据）

# 进入 else 分支
df_now['cumulative_main_net'] = 0.0  # ← 重置为0（正确，新交易日）
```

**结论**: ✓ **行为正确**，新交易日应该从 0 开始

---

## 潜在问题分析

### 问题1：异步写入导致的数据丢失

**场景**: 程序在异步写入完成前崩溃

```
09:30:15 - 计算完成，提交异步写入
09:30:15.1 - 程序崩溃（异步写入未完成）
09:30:30 - 程序恢复，读取数据
         - Redis: 无 09:30:15 数据
         - MySQL: 无 09:30:15 数据
         - 结果: 累计值从 09:30:12 的 800万 开始
         - 丢失: 09:30:15 的 200万
```

**影响**: 累计值少 200万

### 问题2：时间戳精度问题

**场景**: 多个 tick 在同一秒内

```python
# 时间戳格式: HH:MM:SS
# 如果 1 秒内有多个 tick，后面的会覆盖前面的
```

**当前实现**: 3 秒一个 tick，不会冲突

### 问题3：股票代码不一致

**场景**: 上一时刻有股票 A，当前时刻没有

```python
# 09:30:15: 股票 A 累计值 1000万
# 09:30:30: 股票 A 无交易，不在 df_now 中

# 结果: 股票 A 不会更新累计值（正确）
# 09:30:45: 股票 A 有交易
# 读取 09:30:30 的数据，但股票 A 不在其中
# 结果: 股票 A 累计值从 0 开始（错误！）
```

**根本原因**: `how='left'` 合并，股票 A 在 09:30:30 无数据

---

## 解决方案

### 方案1：增强数据可靠性（推荐）⭐

**思路**: 
1. 关键字段同步写入（已在前一个方案中提出）
2. 增加数据校验机制
3. 使用 WAL（Write-Ahead Logging）模式

**实施**:

```python
# 1. 同步写入关键字段（已在前一个方案中）
def save_critical_fields_sync(df, table_name, time_full):
    critical_cols = ['stock_code', 'cumulative_main_net', 'main_net_count', 'max_cumulative_main_net']
    df_critical = df[critical_cols].copy()
    redis_util.save_dataframe_to_redis(df_critical, table_name, time_full, expire_seconds=3600)

# 2. 增加写入确认机制
def save_with_confirmation(df, table_name, time_full, max_retries=3):
    """保存数据并确认写入成功"""
    for i in range(max_retries):
        try:
            # 同步写入
            save_critical_fields_sync(df, table_name, time_full)
            
            # 确认写入成功
            df_check = redis_util.load_dataframe_by_time(table_name, time_full)
            if df_check is not None and not df_check.empty:
                return True
            
            logger.warning(f"写入确认失败，重试 {i+1}/{max_retries}")
            time.sleep(0.01 * (i + 1))  # 指数退避
        except Exception as e:
            logger.error(f"写入失败: {e}")
    
    return False

# 3. 主流程中使用
if not save_with_confirmation(df_now, sssj_table, time_full):
    logger.error(f"[{time_full}] 数据写入失败，跳过本次计算")
    return  # 不计算，等待下一个 tick
```

### 方案2：跨时刻数据恢复

**思路**: 如果当前时刻找不到上一时刻数据，继续往前找

```python
def get_prev_data_with_lookback(table_name, current_time, lookback_minutes=5):
    """
    获取上一时刻数据，支持向前查找
    
    Args:
        table_name: 表名
        current_time: 当前时间
        lookback_minutes: 向前查找的最大分钟数
    
    Returns:
        (prev_time, df) 或 (None, None)
    """
    # 解析当前时间
    current = datetime.strptime(current_time, "%H:%M:%S")
    
    # 向前查找
    for i in range(lookback_minutes * 20):  # 每 3 秒一个 tick，1 分钟 20 个
        lookback_time = (current - timedelta(seconds=i * 3)).strftime("%H:%M:%S")
        
        # 尝试读取
        df = redis_util.load_dataframe_by_time(table_name, lookback_time)
        if df is not None and not df.empty:
            return lookback_time, df
        
        # Redis 失败，尝试 MySQL
        try:
            query = text(f"SELECT * FROM {table_name} WHERE time = '{lookback_time}'")
            df = pd.read_sql(query, engine)
            if not df.empty:
                return lookback_time, df
        except:
            pass
    
    return None, None
```

**使用**:
```python
prev_time, df_prev_main = get_prev_data_with_lookback(sssj_table, time_full, lookback_minutes=5)
if df_prev_main is not None:
    # 使用找到的数据
    pass
else:
    # 真的无数据，从 0 开始
    pass
```

### 方案3：日终数据归档

**思路**: 每日收盘时，将最终累计值归档，次日开盘时读取

```python
# 收盘时归档
def archive_daily_final(date_str):
    """归档当日最终累计值"""
    query = f"""
        SELECT stock_code, cumulative_main_net, main_net_count, max_cumulative_main_net
        FROM monitor_gp_sssj_{date_str}
        WHERE time = '15:00:00'
    """
    df_final = pd.read_sql(query, engine)
    
    # 保存到归档表
    df_final.to_sql(f"monitor_gp_archive_{date_str}", engine, if_exists='replace', index=False)
    
    # 同时保存到 Redis（长期存储）
    redis_util.save_dataframe_to_redis(df_final, f"monitor_gp_archive", date_str, expire_seconds=30*24*3600)

# 次日开盘时读取
def get_opening_balance(date_str):
    """获取开盘时的累计值（上日收盘）"""
    prev_date = get_prev_trading_day(date_str)
    
    # 尝试 Redis
    df = redis_util.load_dataframe_by_key(f"monitor_gp_archive:{prev_date}")
    if df is not None:
        return df
    
    # 尝试 MySQL 归档表
    try:
        query = f"SELECT * FROM monitor_gp_archive_{prev_date}"
        return pd.read_sql(query, engine)
    except:
        pass
    
    return None
```

### 方案4：数据完整性校验

**思路**: 计算数据哈希，校验数据完整性

```python
import hashlib

def calculate_data_hash(df):
    """计算数据哈希"""
    data_str = df.to_json(sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()

def save_with_integrity_check(df, table_name, time_full):
    """保存数据并记录哈希"""
    # 计算哈希
    data_hash = calculate_data_hash(df)
    
    # 保存数据
    redis_util.save_dataframe_to_redis(df, table_name, time_full)
    
    # 保存哈希
    redis_client.set(f"{table_name}:{time_full}:hash", data_hash)

def verify_data_integrity(table_name, time_full):
    """验证数据完整性"""
    df = redis_util.load_dataframe_by_time(table_name, time_full)
    if df is None:
        return False
    
    stored_hash = redis_client.get(f"{table_name}:{time_full}:hash")
    if stored_hash is None:
        return False
    
    current_hash = calculate_data_hash(df)
    return stored_hash == current_hash
```

---

## 推荐方案

### 综合方案：同步关键字段 + 向前查找 + 日终归档

**理由**:
1. **同步关键字段**: 确保核心数据立即写入，不丢失
2. **向前查找**: 如果上一时刻数据丢失，继续往前找，不放弃
3. **日终归档**: 跨交易日时，能正确读取上日收盘数据

**实施步骤**:

1. **同步写入关键字段**（已在第一个方案中）

2. **增强数据获取逻辑**:
```python
# 修改 monitor_stock.py 第 1995-2010 行
df_prev_main = None
prev_time_found = None

if not is_auction:
    # 1. 尝试向前查找（最多 5 分钟）
    prev_time_found, df_prev_main = get_prev_data_with_lookback(
        sssj_table, time_full, lookback_minutes=5
    )
    
    if df_prev_main is not None:
        logger.info(f"[{time_full}] 找到上一时刻数据: {prev_time_found}")
    else:
        # 2. 尝试读取日终归档（跨交易日场景）
        df_prev_main = get_opening_balance(date_str)
        if df_prev_main is not None:
            logger.info(f"[{time_full}] 使用上日收盘数据")
```

3. **增加数据校验**:
```python
# 保存时校验
if not save_with_confirmation(df_now, sssj_table, time_full):
    logger.error(f"[{time_full}] 数据写入失败，使用备用存储")
    # 使用本地文件备用存储
    df_now.to_parquet(f"/tmp/backup_{sssj_table}_{time_full}.parquet")
```

---

## 验证方案

### 测试用例1：程序中断 15 秒

**步骤**:
1. 09:30:00 运行，累计值 1000万
2. 09:30:15 中断程序
3. 09:30:30 恢复程序

**预期**:
- 找到 09:30:12 的数据（或更早）
- 累计值正确叠加

### 测试用例2：Redis 清空

**步骤**:
1. 运行一段时间，产生累计值
2. 清空 Redis
3. 继续运行

**预期**:
- 从 MySQL 读取数据
- 累计值正确叠加

### 测试用例3：跨交易日

**步骤**:
1. 收盘时累计值 5000万
2. 次日开盘

**预期**:
- 新交易日从 0 开始（正确）
- 或从上日收盘继续（如果业务需要）

---

## 总结

| 场景 | 当前行为 | 修复后行为 |
|------|----------|------------|
| 程序中断 15 秒 | ✓ 正确叠加 | ✓ 正确叠加（增强可靠性） |
| 程序中断 1 小时 | ✓ 正确叠加 | ✓ 正确叠加（向前查找） |
| Redis 丢失 | ✓ MySQL 备用 | ✓ MySQL 备用（已支持） |
| Redis + MySQL 丢失 | ✗ 从 0 开始 | ✓ 向前查找 5 分钟 |
| 跨交易日 | ✓ 从 0 开始 | ✓ 从 0 开始（正确） |

**结论**: 当前实现已经**基本支持**程序中断后的累计值叠加，但在极端情况下（Redis + MySQL 都丢失）会失败。推荐实施**向前查找**方案，增强鲁棒性。

---

*分析报告完成*
