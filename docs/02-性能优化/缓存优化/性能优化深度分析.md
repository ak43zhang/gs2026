# monitor_stock.py 性能优化深度分析

## 一、当前性能现状

### 1.1 代码规模
- 总行数: ~2000+ 行
- 主要函数: 20+
- 核心处理流程: 数据采集 → 主力净额计算 → 上攻排行 → 存储

### 1.2 当前处理时间估算

基于代码分析，每个周期（3秒）的处理流程：

| 阶段 | 操作 | 估算耗时 | 优化空间 |
|------|------|----------|----------|
| 1 | 获取实时数据 (5000只股票) | ~1.5-2.5s | ⭐⭐⭐ 大 |
| 2 | 涨停判断 (apply) | ~0.5-1.0s | ⭐⭐⭐ 大 |
| 3 | 加载历史数据 (Redis) | ~0.1-0.3s | ⭐⭐ 中 |
| 4 | 主力净额计算 | ~0.3-0.5s | ⭐⭐⭐ 大 |
| 5 | 上攻排行计算 | ~0.2-0.4s | ⭐⭐ 中 |
| 6 | 存储数据 (MySQL+Redis) | ~0.5-1.0s | ⭐⭐⭐ 大 |
| **总计** | | **~3.0-5.7s** | |

**问题**: 当前周期3秒，但处理时间可能超过3秒，导致周期堆积！

---

## 二、性能瓶颈分析

### 瓶颈1: 数据采集 (⭐⭐⭐ 最高优先级)

**当前代码**:
```python
def fetch_all_concurrently(codes):
    batches = batch_codes(codes, BATCH_SIZE)  # 5000/400 = 13批
    all_data = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:  # 13线程
        future_to_batch = {executor.submit(fetch_batch, batch): batch for batch in batches}
        
        for future in as_completed(future_to_batch):  # 等待所有完成
            df = future.result()
            if not df.empty:
                all_data.append(df)
```

**问题**:
1. 同步等待所有批次完成 (`as_completed`)
2. 单批400只，API响应慢
3. 无超时控制，可能阻塞
4. 无缓存，每次都全量获取

**影响**: 1.5-2.5秒

---

### 瓶颈2: 涨停判断 (⭐⭐⭐ 高优先级)

**当前代码**:
```python
df_now['is_zt'] = df_now.apply(
    lambda row: calc_is_zt(row.get('change_pct'), row.get('stock_code', ''), row.get('short_name', '')),
    axis=1
)
```

**问题**:
1. `apply`逐行处理5000次
2. 每行调用3次`get()`方法
3. 无向量化优化

**影响**: 0.5-1.0秒

---

### 瓶颈3: 主力净额计算 (⭐⭐⭐ 高优先级)

**当前代码**:
```python
# 4.6 判断主力行为 (逐行apply)
behavior_results = valid_data.apply(
    lambda row: classify_main_force_behavior(...),
    axis=1
)

# 4.7 计算参与系数 (逐行apply)
valid_data['participation'] = valid_data['delta_amount'].apply(calculate_participation_ratio)
```

**问题**:
1. 两次`apply`逐行处理
2. `classify_main_force_behavior`复杂逻辑
3. 可向量化但未优化

**影响**: 0.3-0.5秒

---

### 瓶颈4: 数据存储 (⭐⭐⭐ 高优先级)

**当前代码**:
```python
def save_dataframe(df, table_name, time_full, expire_seconds):
    # 1. 写入 MySQL (同步阻塞)
    df.to_sql(table_name, con=engine, if_exists='append', ...)
    
    # 2. 写入 Redis (同步)
    redis_util.save_dataframe_to_redis(df, table_name, time_full, ...)
```

**问题**:
1. MySQL写入同步阻塞
2. 每次都要dtype映射计算
3. 无批量/异步优化

**影响**: 0.5-1.0秒

---

### 瓶颈5: 内存使用 (⭐⭐ 中优先级)

**问题**:
1. 同时持有df_now, df_prev, df_prev_main多个大DataFrame
2. 无及时释放
3. 列类型转换产生临时DataFrame

**影响**: 内存峰值高，可能触发GC

---

## 三、优化方案

### 方案1: 数据采集优化 (⭐⭐⭐ 最高优先级)

#### 1.1 增加超时控制

```python
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

def fetch_all_concurrently(codes, timeout=2.0):
    """增加超时控制"""
    batches = batch_codes(codes, BATCH_SIZE)
    all_data = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_batch = {executor.submit(fetch_batch, batch): batch for batch in batches}
        
        # 设置总体超时
        deadline = time.time() + timeout
        
        for future in as_completed(future_to_batch):
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.warning(f"数据采集超时，已获取{len(all_data)}批")
                break
            
            try:
                df = future.result(timeout=max(0.1, remaining))
                if not df.empty:
                    all_data.append(df)
            except TimeoutError:
                logger.warning(f"单批数据采集超时")
                continue
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()
```

**预期提升**: 1.5-2.5s → 1.0-1.5s (节省0.5-1.0s)

#### 1.2 增量缓存策略

```python
# 缓存最近获取的数据
_data_cache = {}
_cache_time = None

def fetch_all_concurrently_with_cache(codes, cache_ttl=1.0):
    """带缓存的数据获取"""
    global _data_cache, _cache_time
    
    # 检查缓存是否有效
    if _cache_time and (time.time() - _cache_time) < cache_ttl:
        # 使用缓存，只获取变化的股票
        cached_codes = set(_data_cache.keys())
        new_codes = set(codes) - cached_codes
        
        if not new_codes:
            # 完全使用缓存
            return pd.DataFrame.from_dict(_data_cache, orient='index')
        
        # 部分更新
        new_data = fetch_all_concurrently(list(new_codes))
        if not new_data.empty:
            for _, row in new_data.iterrows():
                _data_cache[row['stock_code']] = row.to_dict()
            _cache_time = time.time()
        
        return pd.DataFrame.from_dict(_data_cache, orient='index')
    
    # 无缓存或过期，全量获取
    df = fetch_all_concurrently(codes)
    if not df.empty:
        _data_cache = {row['stock_code']: row.to_dict() for _, row in df.iterrows()}
        _cache_time = time.time()
    
    return df
```

**预期提升**: 减少重复获取，提升20-30%

---

### 方案2: 涨停判断向量化 (⭐⭐⭐ 高优先级)

#### 2.1 替换apply为向量化

```python
# 当前代码 (慢)
df_now['is_zt'] = df_now.apply(lambda row: calc_is_zt(...), axis=1)

# 优化后 (快10倍+)
def calc_is_zt_vectorized(df):
    """向量化涨停判断"""
    # 创业板/科创板: 20%涨停
    # 主板/ST: 10%涨停
    
    # 提取代码前缀
    code_prefix = df['stock_code'].str[:3]
    
    # 判断涨停幅度
    zt_limit = np.where(
        code_prefix.isin(['300', '301', '688', '689']),  # 创业板/科创板
        20.0,
        np.where(df['short_name'].str.contains('ST', na=False), 5.0, 10.0)  # ST股5%，其他10%
    )
    
    # 判断是否涨停
    is_zt = (df['change_pct'] >= zt_limit - 0.5) & (df['change_pct'] > 0)
    
    return is_zt.astype(int)

df_now['is_zt'] = calc_is_zt_vectorized(df_now)
```

**预期提升**: 0.5-1.0s → 0.05-0.1s (节省0.4-0.9s)

---

### 方案3: 主力净额计算优化 (⭐⭐⭐ 高优先级)

#### 3.1 行为分类向量化

```python
# 当前代码 (慢)
behavior_results = valid_data.apply(
    lambda row: classify_main_force_behavior(...), axis=1
)

# 优化后 (快5-10倍)
def classify_main_force_behavior_vectorized(df, time_of_day):
    """向量化主力行为分类"""
    
    # 初始化结果
    result = pd.DataFrame({
        'type': ['不确定'] * len(df),
        'direction': [0.0] * len(df),
        'confidence': [0.0] * len(df)
    })
    
    # 场景1: 极高位置 + 急涨 + 极端放量 → 拉高出货
    mask1 = (df['price_position'] >= 0.98) & (df['price_change_pct'] >= 1.0) & (df['volume_ratio'] >= 5)
    result.loc[mask1, ['type', 'direction', 'confidence']] = ['拉高出货', -1.0, 0.85]
    
    # 场景2: 低位 + 放量上涨 → 真正拉升
    mask2 = (df['price_position'] <= 0.3) & (df['price_change_pct'] >= 0.3) & (df['volume_ratio'] >= 2) & ~mask1
    result.loc[mask2, ['type', 'direction', 'confidence']] = ['真正拉升', 1.0, 0.80]
    
    # 场景3: 低位 + 放量下跌 → 打压吸筹
    mask3 = (df['price_position'] <= 0.3) & (df['price_change_pct'] <= -0.5) & (df['volume_ratio'] >= 2) & ~mask1 & ~mask2
    result.loc[mask3, ['type', 'direction', 'confidence']] = ['打压吸筹', 1.0, 0.80]
    
    # 场景4: 高位 + 放量下跌 → 恐慌抛售
    mask4 = (df['price_position'] >= 0.9) & (df['price_change_pct'] <= -0.5) & (df['volume_ratio'] >= 2) & ~mask1 & ~mask2 & ~mask3
    result.loc[mask4, ['type', 'direction', 'confidence']] = ['恐慌抛售', -1.0, 0.75]
    
    # 场景5-11: 类似处理...
    # 涨停、早盘、尾盘等场景
    
    return result

# 使用
behavior_df = classify_main_force_behavior_vectorized(valid_data, time_of_day)
valid_data['main_behavior'] = behavior_df['type']
valid_data['direction'] = behavior_df['direction']
valid_data['confidence'] = behavior_df['confidence']
```

**预期提升**: 0.3-0.5s → 0.05-0.1s (节省0.2-0.4s)

#### 3.2 参与系数向量化

```python
# 当前代码 (慢)
valid_data['participation'] = valid_data['delta_amount'].apply(calculate_participation_ratio)

# 优化后 (快10倍+)
def calculate_participation_ratio_vectorized(delta_amount):
    """向量化参与系数计算"""
    participation = np.zeros(len(delta_amount))
    
    # level4: >=200万
    mask4 = delta_amount >= 2000000
    participation[mask4] = 1.0
    
    # level3: 100-200万
    mask3 = (delta_amount >= 1000000) & (delta_amount < 2000000) & ~mask4
    participation[mask3] = 0.8 + (delta_amount[mask3] - 1000000) / 1000000 * 0.2
    
    # level2: 50-100万
    mask2 = (delta_amount >= 500000) & (delta_amount < 1000000) & ~mask4 & ~mask3
    participation[mask2] = 0.5 + (delta_amount[mask2] - 500000) / 500000 * 0.3
    
    # level1: 30-50万
    mask1 = (delta_amount >= 300000) & (delta_amount < 500000) & ~mask4 & ~mask3 & ~mask2
    participation[mask1] = 0.3 + (delta_amount[mask1] - 300000) / 200000 * 0.2
    
    # <30万: 0
    
    return participation

valid_data['participation'] = calculate_participation_ratio_vectorized(valid_data['delta_amount'].values)
```

**预期提升**: 0.1-0.2s → 0.01-0.02s (节省0.1-0.2s)

---

### 方案4: 存储优化 (⭐⭐⭐ 高优先级)

#### 4.1 异步存储

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 全局线程池
_storage_executor = ThreadPoolExecutor(max_workers=2)

def save_dataframe_async(df, table_name, time_full, expire_seconds):
    """异步存储数据"""
    # 提交异步任务
    _storage_executor.submit(_save_dataframe_impl, df, table_name, time_full, expire_seconds)

def _save_dataframe_impl(df, table_name, time_full, expire_seconds):
    """实际存储实现"""
    try:
        # MySQL
        df.to_sql(...)
        # Redis
        redis_util.save_dataframe_to_redis(...)
    except Exception as e:
        logger.error(f"存储失败: {e}")
```

**预期提升**: 0.5-1.0s → 0.1-0.2s (节省0.4-0.8s)

#### 4.2 批量存储优化

```python
# 缓存待写入数据
_pending_mysql = []
_pending_redis = []
_last_flush = time.time()

def save_dataframe_batch(df, table_name, time_full, expire_seconds, batch_interval=3.0):
    """批量存储，减少IO次数"""
    global _pending_mysql, _pending_redis, _last_flush
    
    # 加入待写入队列
    _pending_mysql.append((df, table_name))
    _pending_redis.append((df, table_name, time_full, expire_seconds))
    
    # 检查是否达到刷新间隔
    if time.time() - _last_flush >= batch_interval:
        _flush_pending_data()
        _last_flush = time.time()

def _flush_pending_data():
    """刷新待写入数据"""
    global _pending_mysql, _pending_redis
    
    if _pending_mysql:
        # 批量写入MySQL
        combined_df = pd.concat([item[0] for item in _pending_mysql], ignore_index=True)
        combined_df.to_sql(...)
        _pending_mysql = []
    
    if _pending_redis:
        # 批量写入Redis
        for df, table_name, time_full, expire in _pending_redis:
            redis_util.save_dataframe_to_redis(df, table_name, time_full, expire)
        _pending_redis = []
```

**预期提升**: 减少50%的IO次数

---

### 方案5: 内存优化 (⭐⭐ 中优先级)

#### 5.1 及时释放内存

```python
# 当前代码 (内存占用高)
df_now = fetch_all_concurrently(...)
df_prev = redis_util.load_dataframe_by_offset(...)
df_prev_main = redis_util.load_dataframe_by_time(...)
# ... 同时使用3个大DataFrame

# 优化后 (及时释放)
df_now = fetch_all_concurrently(...)

# 使用df_prev_main后立即释放df_prev
df_prev_main = redis_util.load_dataframe_by_time(...)
del df_prev  # 释放内存
gc.collect()

# 计算完成后释放中间结果
result = calculate_main_force_and_cumulative(df_now, df_prev_main, ...)
del df_prev_main
gc.collect()
```

#### 5.2 数据类型优化

```python
# 当前代码 (内存占用大)
df['stock_code'] = df['stock_code'].astype(str)  # 对象类型，占用大

# 优化后 (内存占用小)
df['stock_code'] = df['stock_code'].astype('category')  # 类别类型，占用小

# 数值类型优化
df['main_net_amount'] = df['main_net_amount'].astype('float32')  # 32位而非64位
```

**预期提升**: 内存占用减少30-50%

---

## 四、优化效果预测

### 优化前后对比

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 数据采集 | 1.5-2.5s | 1.0-1.5s | 0.5-1.0s |
| 涨停判断 | 0.5-1.0s | 0.05-0.1s | 0.4-0.9s |
| 主力净额计算 | 0.3-0.5s | 0.05-0.1s | 0.2-0.4s |
| 数据存储 | 0.5-1.0s | 0.1-0.2s | 0.4-0.8s |
| **总计** | **3.0-5.7s** | **1.2-1.9s** | **1.8-3.8s** |

### 关键指标

- **周期**: 3秒
- **当前处理时间**: 3.0-5.7秒（可能超时）
- **优化后处理时间**: 1.2-1.9秒（安全余量1.1-1.8秒）
- **提升**: **60-70%**

---

## 五、实施建议

### 优先级排序

| 优先级 | 优化项 | 预期节省 | 实施难度 | 风险 |
|--------|--------|----------|----------|------|
| P0 | 涨停判断向量化 | 0.4-0.9s | 低 | 低 |
| P0 | 主力净额向量化 | 0.2-0.4s | 中 | 中 |
| P1 | 数据采集超时 | 0.5-1.0s | 低 | 低 |
| P1 | 存储异步化 | 0.4-0.8s | 中 | 中 |
| P2 | 内存优化 | - | 低 | 低 |
| P2 | 增量缓存 | 20-30% | 中 | 中 |

### 分阶段实施

**第一阶段 (P0)**:
1. 涨停判断向量化
2. 主力净额向量化

**第二阶段 (P1)**:
3. 数据采集超时控制
4. 存储异步化

**第三阶段 (P2)**:
5. 内存优化
6. 增量缓存

---

## 六、审核确认

### 优化方案总结

| 方案 | 核心改进 | 预期效果 | 风险 |
|------|----------|----------|------|
| 向量化计算 | 替换apply | 节省1.0-1.5s | 低 |
| 超时控制 | 防止阻塞 | 节省0.5-1.0s | 低 |
| 异步存储 | 非阻塞IO | 节省0.4-0.8s | 中 |
| 内存优化 | 减少GC | 提升稳定性 | 低 |

### 推荐实施

**立即实施**: P0级优化（向量化计算）
- 改动小，效果明显
- 风险可控
- 可节省1.0-1.5秒

**后续实施**: P1级优化（超时控制、异步存储）

---

**请审核通过后，我将立即实施P0级优化。**
