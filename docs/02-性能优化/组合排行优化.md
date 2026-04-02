# get_combine_ranking 性能优化分析方案

> 分析时间: 2026-03-31 00:40  
> 目标: 分析股债联动信号查询性能瓶颈，给出优化方案

---

## 1. 当前实现分析

### 1.1 代码位置
`src/gs2026/dashboard/services/data_service.py` - `get_combine_ranking` 方法 (约第520行起)

### 1.2 当前数据流

```
GET /api/monitor/combine
  ↓
get_combine() [monitor.py]
  ↓
data_service.get_combine_ranking(limit=50, date=None, time_str=None)
  ↓
  ├─→ 1. Redis查询（优先）
  │     ├─→ 获取时间戳列表 (llen + lrange)
  │     ├─→ 遍历时间戳（最多200个）
  │     ├─→ 每个时间戳加载DataFrame (load_dataframe_by_key)
  │     ├─→ 遍历DataFrame行去重 (code+name+time)
  │     └─→ 计算买入/卖出价格
  │
  └─→ 2. MySQL查询（fallback）
        ├─→ 执行SQL查询
        ├─→ 遍历结果计算价格
        └─→ 返回数据
```

### 1.3 性能瓶颈识别

| 瓶颈点 | 严重程度 | 说明 |
|--------|----------|------|
| **Redis循环加载** | ⭐⭐⭐⭐⭐ | 最多200次时间戳 × 每次加载DataFrame |
| **DataFrame重复加载** | ⭐⭐⭐⭐ | 相同数据可能被多次加载 |
| **Python循环去重** | ⭐⭐⭐ | 用set去重，但循环遍历行 |
| **价格计算** | ⭐⭐ | 简单数学运算，开销小 |
| **MySQL查询** | ⭐⭐ | 有索引时很快 |

---

## 2. 详细瓶颈分析

### 瓶颈1: Redis循环加载（最严重）

```python
# 当前实现 - 问题代码
total_ts = client.llen(ts_list_key)  # 1次查询
all_ts = client.lrange(ts_list_key, 0, min(total_ts, 200) - 1)  # 1次查询

for ts_data in all_ts:  # 最多200次循环
    ts = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    
    key = f"{table_name}:{ts}"
    df = redis_util.load_dataframe_by_key(key, use_compression=False)  # 200次DataFrame加载！
    
    if df is not None and not df.empty:
        for _, row in df.iterrows():  # 遍历每行
            # ... 去重逻辑
```

**问题**:
- 最多200次Redis查询
- 每次查询都反序列化DataFrame
- 假设每帧50条数据，200帧 = 10,000行遍历

### 瓶颈2: 数据重复加载

```python
# 每次请求都从Redis重新加载
# 没有应用层缓存
# 相同数据短时间内被多次查询
```

### 瓶颈3: 去重逻辑

```python
# 当前实现
seen_keys = set()
for _, row in df.iterrows():
    dedup_key = f"{row.get('code', '')}_{row.get('name', '')}_{row.get('time', ts)}"
    if dedup_key in seen_keys:
        continue
    seen_keys.add(dedup_key)
```

**问题**:
- 字符串拼接开销
- 虽然set查找O(1)，但遍历所有行

---

## 3. 优化方案设计

### 方案A: 应用内存缓存（推荐）

```python
# 添加应用层内存缓存，5秒过期
import time
import threading

class CombineDataCache:
    """股债联动数据内存缓存"""
    
    def __init__(self, ttl=5):
        self._cache = {}
        self._lock = threading.RLock()
        self._ttl = ttl
    
    def get(self, date, time_str=None, limit=50):
        """获取缓存数据"""
        cache_key = f"{date}:{time_str}:{limit}"
        with self._lock:
            if cache_key in self._cache:
                data, expiry = self._cache[cache_key]
                if time.time() < expiry:
                    return data
                else:
                    del self._cache[cache_key]
            return None
    
    def set(self, date, time_str, limit, data):
        """设置缓存"""
        cache_key = f"{date}:{time_str}:{limit}"
        with self._lock:
            self._cache[cache_key] = (data, time.time() + self._ttl)
    
    def clear(self):
        """清理缓存"""
        with self._lock:
            self._cache.clear()

# 全局缓存实例
_combine_cache = CombineDataCache(ttl=5)  # 5秒过期

# 修改 get_combine_ranking
def get_combine_ranking(self, limit=50, date=None, time_str=None):
    if date is None:
        date = self.get_latest_date()
    
    # 1. 检查内存缓存
    cached = _combine_cache.get(date, time_str, limit)
    if cached:
        return cached
    
    # 2. 原有查询逻辑...
    result = self._query_combine_data(limit, date, time_str)
    
    # 3. 写入缓存
    _combine_cache.set(date, time_str, limit, result)
    
    return result
```

**预期效果**: 5秒内相同请求直接返回缓存，响应时间从秒级降至毫秒级

---

### 方案B: Redis数据结构优化

当前Redis存储结构：
```
monitor_combine_20260330:timestamps -> List["09:30:00", "09:30:03", ...]
monitor_combine_20260330:09:30:00 -> DataFrame序列化数据
monitor_combine_20260330:09:30:03 -> DataFrame序列化数据
...
```

**问题**: 需要遍历所有时间戳

优化方案 - 增加聚合key：
```python
# 在写入Redis时，同时写入聚合数据
# 只保留最新50条

def update_combine_redis(df, date=None):
    """更新股债联动Redis数据"""
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    table_name = f"monitor_combine_{date}"
    
    # 原有逻辑：按时间戳存储
    # ...
    
    # 新增：维护一个聚合列表，只保留最新50条
    client = redis_util._get_redis_client()
    
    # 获取当前聚合数据
    agg_key = f"{table_name}:latest"
    existing = client.get(agg_key)
    
    if existing:
        existing_data = json.loads(existing)
    else:
        existing_data = []
    
    # 合并新数据（去重）
    new_records = df.to_dict('records')
    all_records = new_records + existing_data
    
    # 去重并保留最新50条
    seen = set()
    unique_records = []
    for record in all_records:
        key = f"{record.get('code', '')}_{record.get('time', '')}"
        if key not in seen:
            seen.add(key)
            unique_records.append(record)
    
    # 按时间倒序，保留50条
    unique_records.sort(key=lambda x: x.get('time', ''), reverse=True)
    final_records = unique_records[:50]
    
    # 写入Redis
    client.setex(agg_key, 3600, json.dumps(final_records))
    
    return final_records

# 查询时直接使用聚合key
def get_combine_ranking_fast(self, limit=50, date=None, time_str=None):
    """快速查询 - 使用聚合数据"""
    if date is None:
        date = self.get_latest_date()
    
    table_name = f"monitor_combine_{date}"
    agg_key = f"{table_name}:latest"
    
    try:
        client = redis_util._get_redis_client()
        data = client.get(agg_key)
        
        if data:
            records = json.loads(data)
            
            # 时间过滤
            if time_str:
                records = [r for r in records if r.get('time', '') <= time_str]
            
            # 计算价格
            for record in records[:limit]:
                price_now = record.get('price_now_zq', 0)
                if price_now:
                    price_1decimal = round(price_now, 1)
                    record['buy_price'] = round(price_1decimal + 0.1, 2)
                    record['sell_price'] = round(price_1decimal + 0.5, 2)
            
            return records[:limit]
    except Exception as e:
        print(f"Fast query failed: {e}")
    
    # fallback到原方法
    return self.get_combine_ranking(limit, date, time_str)
```

**预期效果**: 从200次Redis查询降至1次，响应时间从秒级降至10-50ms

---

### 方案C: 批量加载优化

```python
# 优化Redis加载 - 使用pipeline批量获取

def get_combine_ranking_optimized(self, limit=50, date=None, time_str=None):
    """优化版 - 使用pipeline批量加载"""
    if date is None:
        date = self.get_latest_date()
    
    table_name = f"monitor_combine_{date}"
    
    try:
        client = redis_util._get_redis_client()
        
        # 1. 获取时间戳列表
        ts_list_key = f"{table_name}:timestamps"
        total_ts = client.llen(ts_list_key)
        
        if total_ts == 0:
            raise Exception("No timestamps in Redis")
        
        # 2. 获取时间戳（限制数量）
        all_ts = client.lrange(ts_list_key, 0, min(total_ts, 50) - 1)  # 减少到50个
        
        # 3. 构建key列表
        keys = []
        for ts_data in all_ts:
            ts = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
            if time_str and ts > time_str:
                continue
            keys.append(f"{table_name}:{ts}")
        
        # 4. 使用pipeline批量获取（关键优化！）
        pipe = client.pipeline()
        for key in keys:
            pipe.get(key)
        
        results = pipe.execute()  # 1次网络往返获取所有数据！
        
        # 5. 处理数据
        seen_keys = set()
        final_records = []
        
        for data in results:
            if not data:
                continue
            
            # 反序列化DataFrame
            df = redis_util._deserialize_dataframe(data)
            
            if df is None or df.empty:
                continue
            
            for _, row in df.iterrows():
                dedup_key = f"{row.get('code', '')}_{row.get('time', '')}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                
                # 构建记录...
                record = self._build_record(row)
                final_records.append(record)
                
                if len(final_records) >= limit:
                    break
            
            if len(final_records) >= limit:
                break
        
        return final_records
        
    except Exception as e:
        print(f"Optimized query failed: {e}, fallback to MySQL")
        return self._query_combine_from_mysql(limit, date, time_str)
```

**预期效果**: 从200次网络往返降至1次，响应时间从秒级降至100-200ms

---

### 方案D: MySQL查询优化（fallback）

```sql
-- 检查当前索引
SHOW INDEX FROM monitor_combine_20260330;

-- 添加复合索引（如果不存在）
ALTER TABLE monitor_combine_20260330 
ADD INDEX idx_time_code (time, code);

-- 添加覆盖索引（可选）
ALTER TABLE monitor_combine_20260330 
ADD INDEX idx_query (time, code, name, code_gp, name_gp, price_now_zq);
```

```python
# 优化MySQL查询 - 只查询必要字段
query = f"""
    SELECT 
        time, 
        code, 
        name, 
        code_gp, 
        name_gp, 
        price_now_zq, 
        zf_30, 
        zf_30_zq
    FROM {table_name}
    WHERE time <= %s
    ORDER BY time DESC
    LIMIT %s
"""

# 使用参数化查询防止SQL注入
with self.engine.connect() as conn:
    df = pd.read_sql(query, conn, params=(time_str or '23:59:59', limit))
```

---

## 4. 综合优化方案（推荐组合）

### 最优组合: 方案A + 方案B + 方案D

```
┌─────────────────────────────────────────────────────────┐
│  查询请求                                                │
│     ↓                                                   │
│  ┌──────────────┐                                       │
│  │ L1: 内存缓存  │ ← 5秒过期，命中直接返回（<1ms）        │
│  └──────────────┘                                       │
│     ↓ 未命中                                            │
│  ┌──────────────────┐                                   │
│  │ L2: Redis聚合key  │ ← 1次查询获取50条（10-50ms）       │
│  └──────────────────┘                                   │
│     ↓ 未命中                                            │
│  ┌──────────────────┐                                   │
│  │ L3: Redis原始数据 │ ← Pipeline批量加载（100-200ms）    │
│  └──────────────────┘                                   │
│     ↓ 未命中                                            │
│  ┌──────────────────┐                                   │
│  │ L4: MySQL查询     │ ← 索引优化（50-100ms）             │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

### 实施代码

```python
# data_service.py

import time
import threading
import json

class CombineDataCache:
    """股债联动数据多级缓存"""
    
    def __init__(self, memory_ttl=5):
        self._memory_cache = {}
        self._memory_lock = threading.RLock()
        self._memory_ttl = memory_ttl
    
    def get_from_memory(self, date, time_str, limit):
        """L1: 内存缓存"""
        cache_key = f"{date}:{time_str}:{limit}"
        with self._memory_lock:
            if cache_key in self._memory_cache:
                data, expiry = self._memory_cache[cache_key]
                if time.time() < expiry:
                    return data
                del self._memory_cache[cache_key]
            return None
    
    def set_to_memory(self, date, time_str, limit, data):
        """写入内存缓存"""
        cache_key = f"{date}:{time_str}:{limit}"
        with self._memory_lock:
            self._memory_cache[cache_key] = (data, time.time() + self._memory_ttl)
    
    def get_from_redis_agg(self, client, table_name, time_str, limit):
        """L2: Redis聚合数据"""
        try:
            agg_key = f"{table_name}:latest"
            data = client.get(agg_key)
            
            if not data:
                return None
            
            records = json.loads(data)
            
            # 时间过滤
            if time_str:
                records = [r for r in records if r.get('time', '') <= time_str]
            
            # 计算价格
            for record in records[:limit]:
                price_now = record.get('price_now_zq', 0)
                if price_now:
                    price_1decimal = round(price_now, 1)
                    record['buy_price'] = round(price_1decimal + 0.1, 2)
                    record['sell_price'] = round(price_1decimal + 0.5, 2)
            
            return records[:limit]
            
        except Exception as e:
            print(f"Redis agg query failed: {e}")
            return None

# 全局缓存实例
_combine_cache = CombineDataCache(memory_ttl=5)


class DataService:
    # ... 原有代码 ...
    
    def get_combine_ranking_optimized(self, limit=50, date=None, time_str=None):
        """
        优化版股债联动信号查询
        
        多级缓存策略:
        1. L1: 应用内存缓存 (5秒)
        2. L2: Redis聚合数据
        3. L3: MySQL查询
        """
        if date is None:
            date = self.get_latest_date()
        
        table_name = f"monitor_combine_{date}"
        
        # L1: 内存缓存
        cached = _combine_cache.get_from_memory(date, time_str, limit)
        if cached:
            return cached
        
        # L2: Redis聚合数据
        if self.redis_available:
            try:
                client = redis_util._get_redis_client()
                result = _combine_cache.get_from_redis_agg(
                    client, table_name, time_str, limit
                )
                if result:
                    # 写入内存缓存
                    _combine_cache.set_to_memory(date, time_str, limit, result)
                    return result
            except Exception as e:
                print(f"L2 cache failed: {e}")
        
        # L3: MySQL查询
        result = self._query_combine_from_mysql(limit, date, time_str)
        
        # 写入内存缓存
        _combine_cache.set_to_memory(date, time_str, limit, result)
        
        return result
    
    def _query_combine_from_mysql(self, limit, date, time_str):
        """从MySQL查询combine数据"""
        table_name = f"monitor_combine_{date}"
        
        try:
            if time_str:
                query = """
                    SELECT time, code, name, code_gp, name_gp, 
                           price_now_zq, zf_30, zf_30_zq
                    FROM {}
                    WHERE time <= %s
                    ORDER BY time DESC
                    LIMIT %s
                """.format(table_name)
                params = (time_str, limit)
            else:
                query = """
                    SELECT time, code, name, code_gp, name_gp, 
                           price_now_zq, zf_30, zf_30_zq
                    FROM {}
                    ORDER BY time DESC
                    LIMIT %s
                """.format(table_name)
                params = (limit,)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params=params)
                
                result = []
                for _, row in df.iterrows():
                    price_now = row.get('price_now_zq', 0)
                    if price_now:
                        price_1decimal = round(price_now, 1)
                        buy_price = round(price_1decimal + 0.1, 2)
                        sell_price = round(price_1decimal + 0.5, 2)
                    else:
                        buy_price = None
                        sell_price = None
                    
                    result.append({
                        'time': str(row.get('time', '')),
                        'code': str(row.get('code', '')).zfill(6) if row.get('code') else '',
                        'name': str(row.get('name', '')),
                        'code_gp': str(row.get('code_gp', '')).zfill(6) if row.get('code_gp') else '',
                        'name_gp': str(row.get('name_gp', '')),
                        'price_now_zq': price_now,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'zf_30': row.get('zf_30', None),
                        'zf_30_zq': row.get('zf_30_zq', None),
                    })
                
                return result
                
        except Exception as e:
            print(f"MySQL query failed: {e}")
            return []
```

---

## 5. 预期效果

| 优化项 | 当前 | 优化后 | 提升 |
|--------|------|--------|------|
| 内存缓存命中 | - | < 1ms | ∞ |
| Redis聚合查询 | 200次查询 | 1次查询 | 200x |
| 典型响应时间 | 1-3秒 | 10-50ms | 20-300x |
| MySQL fallback | 100-200ms | 50-100ms | 2x |

---

## 6. 实施计划

### 阶段1: 快速优化（1小时）
- [ ] 添加应用内存缓存（方案A）
- [ ] 修改 `get_combine_ranking` 使用缓存
- [ ] 测试验证

### 阶段2: Redis优化（2小时）
- [ ] 修改数据写入逻辑，添加聚合key
- [ ] 实现 `get_from_redis_agg` 方法
- [ ] 测试验证

### 阶段3: MySQL优化（1小时）
- [ ] 添加数据库索引
- [ ] 优化查询语句
- [ ] 测试验证

### 阶段4: 监控（持续）
- [ ] 添加性能监控日志
- [ ] 观察线上效果

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 缓存数据不一致 | 低 | 中 | 5秒短过期时间 |
| 内存占用增加 | 低 | 低 | 限制缓存大小 |
| Redis聚合key未命中 | 中 | 低 | fallback到MySQL |

---

**文档位置**: `docs/get_combine_ranking_optimization.md`

**建议**: 先实施阶段1（内存缓存），可立即获得显著性能提升。
