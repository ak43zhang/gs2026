# Bug 深度分析：Tick 数据丢失导致累计值断裂

## 问题描述

**场景**:
- 09:30:15 - 主力资金: 1000万
- 09:30:18 - **数据丢失**（tick 缺失）
- 09:30:21 - 获取到数据，但累计值从 0 开始计算

**结果**: 前面的 1000万没有叠加到后面，累计值断裂。

---

## 数据流分析

### 正常流程

```
时间        当前净额    上一累计    新累计      存储
09:30:15    1000万      0          1000万      ✓
09:30:18    500万       1000万     1500万      ✓
09:30:21    300万       1500万     1800万      ✓
```

### 异常流程（09:30:18 数据丢失）

```
时间        当前净额    上一累计    新累计      存储
09:30:15    1000万      0          1000万      ✓ 写入 Redis/MySQL
09:30:18    -           -          -           ✗ 数据丢失
09:30:21    300万       ???        ???         ?
```

**问题**: 09:30:21 如何获取"上一累计"？

---

## 当前实现分析

### 1. 数据获取逻辑

**文件**: `monitor_stock.py` 第 1995-2010 行

```python
# 【新增】df_prev_main 用于主力净额计算（时间戳查询）
df_prev_main = None
if not is_auction:
    try:
        # 找上一个有数据的时间点（非15秒周期）
        prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
        if prev_time:
            df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
            logger.info(f"[{time_full}] 主力净额计算使用时间点: {prev_time}")
```

**逻辑**: 
- 使用 `get_prev_timestamp_with_data` 找上一个**有数据**的时间点
- 09:30:21 会找到 09:30:15（因为 09:30:18 没有数据）

### 2. 累计值计算逻辑

**文件**: `monitor_stock.py` 第 669-692 行

```python
# 【关键】计算累计主力净额
if 'cumulative_main_net' in df_prev_main.columns:
    prev_cumulative = df_prev_main[['stock_code', 'cumulative_main_net']].copy()
    
    if not prev_cumulative.empty:
        df_now = df_now.merge(
            prev_cumulative,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 新的累计值 = 上一累计值 + 当前值
        df_now['cumulative_main_net_prev'] = df_now['cumulative_main_net_prev'].fillna(0)
        df_now['cumulative_main_net'] = df_now['cumulative_main_net_prev'] + df_now['main_net_amount']
```

**预期行为**:
- 09:30:21 获取 09:30:15 的累计值（1000万）
- 新累计值 = 1000万 + 300万 = 1300万 ✓

### 3. 问题排查

**可能的问题点**:

#### 问题 A: Redis 数据未写入

09:30:15 的数据是否成功写入 Redis？

```python
# monitor_stock.py 第 2073 行
save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
```

**异步存储的问题**:
- 数据写入是异步的（后台线程）
- 如果 09:30:18 的数据处理很快，可能 09:30:15 的数据还在写入中
- 但 09:30:21 应该能读到 09:30:15 的数据（3秒足够写入完成）

#### 问题 B: 股票不在 df_prev_main 中

```python
# monitor_stock.py 第 593-598 行
merged = pd.merge(
    df_now[['stock_code', ...]],
    df_prev_main[['stock_code', 'volume', 'amount', 'change_pct']],
    on='stock_code',
    how='inner'  # ← 问题：inner join 可能丢失数据
)
```

**问题**: `how='inner'` 意味着只保留两边都有的股票。

**场景**:
- 09:30:15: 股票 A 有数据（主力资金 1000万）
- 09:30:21: 股票 A 不在当前 tick 中（可能没交易）
- 结果：股票 A 不会出现在 df_now 中

但这不应该是问题，因为用户说的是"获取到数据"...

#### 问题 C: 初始化逻辑覆盖

```python
# monitor_stock.py 第 2039-2050 行（else 分支）
else:
    # 集合竞价或无上一时刻数据
    df_now['main_net_amount'] = 0.0
    df_now['cumulative_main_net'] = 0.0
    # ...
    if is_auction:
        logger.info(f"[{time_full}] 集合竞价，主力净额置0")
    else:
        logger.warning(f"[{time_full}] 无上一时刻数据，主力净额置0")  # ← 关键日志
```

**问题**: 如果 `df_prev_main` 为 None 或 empty，会进入这个分支，累计值重置为 0！

#### 问题 D: 时间戳匹配问题

```python
# redis_util.py 第 960-969 行
timestamps = sorted([...])

# 找当前时间之前的最新时间
for ts in reversed(timestamps):
    if ts < current_time:
        prev_time = ts
        break
```

**问题**: 如果时间戳列表中有 09:30:15 和 09:30:21，但 09:30:15 > 09:30:21 不成立...

等等，时间戳是字符串比较：
- "09:30:21" < "09:30:15"？不成立
- "09:30:15" < "09:30:21"？成立

所以 09:30:21 会找到 09:30:15，没问题。

### 4. 最可能的问题

**问题 C: 初始化逻辑被触发**

**场景推演**:
```
09:30:15: 正常处理，写入 Redis
         save_dataframe_async(df_093015, "monitor_gp_sssj_20260513", "09:30:15", ...)

09:30:18: 数据丢失，跳过处理

09:30:21: 尝试获取上一时刻数据
         prev_time = get_prev_timestamp_with_data("monitor_gp_sssj_20260513", "09:30:21")
         # 应该返回 "09:30:15"
         
         df_prev_main = load_dataframe_by_time(..., "09:30:15")
         # 问题：异步写入可能还没完成？或者读取失败？
         
         if df_prev_main is None or df_prev_main.empty:
             # 进入 else 分支，累计值重置为 0！
             df_now['cumulative_main_net'] = 0.0
```

**根本原因**:
1. 异步写入导致 09:30:15 的数据还没写入完成
2. 或者 Redis 读取失败
3. 导致 `df_prev_main` 为 None 或 empty
4. 触发初始化逻辑，累计值重置为 0

---

## 修复方案

### 方案1：同步写入关键数据（推荐）⭐

**思路**: 将累计值等关键字段改为同步写入，确保下一 tick 能读到。

**修改** `monitor_stock.py`:

```python
# 修改前（异步）
save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)

# 修改后（关键字段同步写入）
def save_dataframe_sync_critical(df, table_name, time_full):
    """同步写入关键字段，确保下一 tick 能读到"""
    critical_cols = ['stock_code', 'cumulative_main_net', 'main_net_count', 'max_cumulative_main_net']
    df_critical = df[critical_cols].copy()
    redis_util.save_dataframe_to_redis(df_critical, table_name, time_full, expire_seconds=3600)

# 同步写入关键字段（阻塞，确保完成）
save_dataframe_sync_critical(df_now, sssj_table, time_full)

# 异步写入完整数据（非阻塞）
save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
```

**优点**:
- 确保关键数据立即写入，下一 tick 可读
- 不影响性能（只同步写入少量字段）

**缺点**:
- 增加一点延迟（但关键字段数据量小，可接受）

### 方案2：使用 MySQL 作为备用源

**思路**: 如果 Redis 读取失败，从 MySQL 读取上一时刻数据。

**修改** `monitor_stock.py` 第 1995-2010 行:

```python
df_prev_main = None
if not is_auction:
    # 1. 尝试从 Redis 读取
    try:
        prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
        if prev_time:
            df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
    except Exception as e:
        logger.warning(f"[{time_full}] Redis读取失败: {e}")
    
    # 2. Redis 失败或无数据，从 MySQL 读取
    if df_prev_main is None or df_prev_main.empty:
        try:
            prev_time = get_prev_timestamp_from_mysql(sssj_table, time_full)
            if prev_time:
                query = f"SELECT * FROM {sssj_table} WHERE time = '{prev_time}'"
                df_prev_main = pd.read_sql(query, engine)
                logger.info(f"[{time_full}] 从MySQL读取上一时刻: {prev_time}")
        except Exception as e:
            logger.warning(f"[{time_full}] MySQL读取失败: {e}")
```

**优点**:
- MySQL 数据更可靠（持久化）
- 不依赖 Redis 写入速度

**缺点**:
- 增加 MySQL 查询压力
- 需要处理时间戳对齐问题

### 方案3：缓存上一时刻数据

**思路**: 在内存中缓存上一时刻的累计值，不依赖外部存储。

**修改** `monitor_stock.py`:

```python
# 全局缓存（进程内）
_last_cumulative_cache = {}

def calculate_main_force_and_cumulative(df_now, df_prev_main, ...):
    # ...
    
    # 优先使用内存缓存
    stock_code = df_now['stock_code'].iloc[0]
    if stock_code in _last_cumulative_cache:
        prev_cumulative = _last_cumulative_cache[stock_code]
    else:
        # 从 df_prev_main 读取
        prev_cumulative = ...
    
    # 计算新累计值
    new_cumulative = prev_cumulative + current_main_net
    
    # 更新缓存
    _last_cumulative_cache[stock_code] = new_cumulative
    
    # ...
```

**优点**:
- 最快，不依赖外部存储
- 不受异步写入影响

**缺点**:
- 进程重启后数据丢失
- 多进程部署时需要共享缓存（如 Redis）

### 方案4：批量写入 + 读取优化

**思路**: 优化写入和读取的时机，确保数据一致性。

**修改**:

```python
# 1. 在计算下一 tick 前，强制等待上一 tick 写入完成
def ensure_data_written(table_name, time_str, timeout=1.0):
    """确保数据已写入 Redis"""
    start = time.time()
    while time.time() - start < timeout:
        df = redis_util.load_dataframe_by_time(table_name, time_str)
        if df is not None and not df.empty:
            return True
        time.sleep(0.01)
    return False

# 2. 在计算 09:30:21 前，确保 09:30:15 已写入
if prev_time:
    if not ensure_data_written(sssj_table, prev_time):
        logger.warning(f"[{time_full}] 上一时刻数据未就绪，使用MySQL备用")
        # 从 MySQL 读取
```

**优点**:
- 确保数据一致性
- 不影响正常流程

**缺点**:
- 增加等待时间
- 需要设置合理的超时

---

## 推荐方案

### 综合方案：同步关键字段 + MySQL 备用

**理由**:
1. **同步关键字段**: 确保累计值等关键数据立即写入，下一 tick 可读
2. **MySQL 备用**: 如果 Redis 读取失败，从 MySQL 读取，双重保障
3. **不影响性能**: 只同步写入少量字段，完整数据仍异步写入

**实施步骤**:

1. **添加同步写入函数**:
```python
def save_critical_fields_sync(df, table_name, time_full):
    """同步写入关键字段"""
    critical_cols = ['stock_code', 'cumulative_main_net', 'main_net_count', 'max_cumulative_main_net']
    df_critical = df[critical_cols].copy()
    redis_util.save_dataframe_to_redis(df_critical, table_name, time_full, expire_seconds=3600)
```

2. **修改主流程**:
```python
# 同步写入关键字段
save_critical_fields_sync(df_now, sssj_table, time_full)

# 异步写入完整数据
save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
```

3. **添加 MySQL 备用读取**:
```python
def get_prev_data_with_fallback(table_name, time_full):
    """获取上一时刻数据，Redis失败时从MySQL读取"""
    prev_time = redis_util.get_prev_timestamp_with_data(table_name, time_full)
    if not prev_time:
        return None
    
    # 尝试 Redis
    df = redis_util.load_dataframe_by_time(table_name, prev_time)
    if df is not None and not df.empty:
        return df
    
    # Redis 失败，尝试 MySQL
    logger.warning(f"Redis读取失败，尝试MySQL: {prev_time}")
    try:
        query = f"SELECT * FROM {table_name} WHERE time = '{prev_time}'"
        return pd.read_sql(query, engine)
    except Exception as e:
        logger.error(f"MySQL读取也失败: {e}")
        return None
```

4. **修改调用**:
```python
df_prev_main = get_prev_data_with_fallback(sssj_table, time_full)
```

---

## 验证方案

### 测试用例

**场景**: 09:30:15 有数据，09:30:18 丢失，09:30:21 恢复

**预期结果**:
```
09:30:15: 当前=1000万, 累计=1000万
09:30:18: 数据丢失，跳过
09:30:21: 当前=300万, 上一累计=1000万, 新累计=1300万 ✓
```

**验证点**:
1. 09:30:15 的关键字段已同步写入 Redis
2. 09:30:21 能从 Redis 读到 09:30:15 的数据
3. 如果 Redis 失败，能从 MySQL 读取
4. 累计值正确计算为 1300万

---

## 总结

| 问题 | 根因 | 修复方案 |
|------|------|----------|
| Tick 丢失导致累计断裂 | 异步写入导致读取时数据未就绪 | 同步关键字段 + MySQL 备用 |
| 累计值重置为 0 | 读取失败进入 else 分支 | 双重保障读取机制 |

---

*分析报告完成*
