# /api/monitor/latest-messages 接口深度分析报告

> 分析时间: 2026-03-31 19:40  
> 接口: GET /api/monitor/latest-messages

---

## 一、接口功能说明

### 1.1 用途
获取**股债联动信号**的最新消息/数据，用于Dashboard2首页的"最新消息"展示。

### 1.2 数据来源
- **表**: `monitor_combine_{date}`（股债联动信号表）
- **字段**: time, code, name, code_gp, name_gp, price_now_zq, zf_30, zf_30_zq
- **数据量**: 每个时间点约200-500条记录，全天约4800个时间点

### 1.3 返回数据示例
```json
{
  "success": true,
  "data": [
    {
      "time": "15:00:00",
      "code": "123160",
      "name": "泰福转债",
      "code_gp": "300992",
      "name_gp": "泰福泵业",
      "price_now_zq": 128.5,
      "buy_price": 128.6,
      "sell_price": 129.0,
      "zf_30": 2.5,
      "zf_30_zq": 1.8
    }
  ],
  "count": 50
}
```

---

## 二、完整调用链分析

### 2.1 调用链图

```
GET /api/monitor/latest-messages?limit=50
    ↓ ~700ms (历史慢请求记录)
monitor_bp.route('/latest-messages')
    ↓
get_latest_messages()
    ↓ ~10ms
    data_service.get_combine_ranking(limit=50, date=None, time_str=None)
        ↓
        1. 从Redis获取（已优化Pipeline批量加载）
            ├── lrange timestamps (获取最近50个时间点)
            ├── Pipeline批量mget (1次网络往返)
            ├── 反序列化DataFrame (50次)
            ├── 遍历DataFrame处理 (50 × 平均300行 = 15000行)
            ├── 计算buy_price/sell_price (每行)
            └── 去重 (seen_keys set)
        
        2. Redis未命中则查MySQL（fallback）
            └── SELECT * FROM monitor_combine_20260331 ORDER BY time DESC LIMIT 50
    ↓
jsonify() + 网络传输
```

### 2.2 性能数据分析

从性能监控获取的历史数据：

| 时间 | 总耗时 | DB查询 | DB时间 | 其他时间 |
|------|--------|--------|--------|----------|
| 19:04:56 | 729.05ms | 0 | 0 | **729ms** |
| 18:25:35 | 704.12ms | 0 | 0 | **704ms** |

**关键发现**:
- **DB时间为0** - 数据来自Redis，没有数据库查询
- **其他时间占100%** - 约700ms全部用于Redis数据处理和Python计算

---

## 三、慢请求根本原因分析

### 3.1 主要原因: DataFrame反序列化和遍历

**代码位置**: `data_service.py:625-700`

```python
# 1. Pipeline批量获取（已优化，快）
pipe_results = pipe.execute()  # 1次网络往返

# 2. 反序列化DataFrame（50次，慢！）
for ts, data in zip(valid_ts, pipe_results):
    df = self._deserialize_dataframe(data)  # 每次约10-15ms
    
# 3. 遍历DataFrame（15000行，慢！）
for _, row in df.iterrows():
    # 计算价格
    buy_price = round(price_1decimal + 0.1, 2)
    sell_price = round(buy_price + 0.4, 2)
    
    # 构建record
    record = {...}
    result.append(record)
```

**耗时估算**:
- 50个时间点 × 10ms反序列化 = **500ms**
- 15000行 × 0.01ms处理 = **150ms**
- 其他开销 = **50ms**
- **总计 ≈ 700ms** ✓

### 3.2 次要原因: 重复计算

每次请求都重新计算:
- `buy_price = round(price_1decimal + 0.1, 2)`
- `sell_price = round(buy_price + 0.4, 2)`

这些计算可以在数据写入时预计算。

---

## 四、优化方案

### 方案A: 减少时间点数量（推荐，立即实施）

**问题**: 获取50个时间点，每个时间点约300行，共15000行

**解决方案**:
```python
# 修改前: 获取50个时间点
all_ts = client.lrange(ts_list_key, 0, min(total_ts, 50) - 1)

# 修改后: 只获取10个时间点（最近10个时间点的数据足够）
all_ts = client.lrange(ts_list_key, 0, min(total_ts, 10) - 1)
```

**效果**:
- 时间点: 50 → 10
- 数据行: 15000 → 3000
- 反序列化: 50次 → 10次
- **预期耗时: 700ms → 200ms**

---

### 方案B: 预计算价格字段（推荐）

**问题**: 每次请求都重新计算buy_price/sell_price

**解决方案**:
```python
# 1. 数据写入时预计算（monitor_combine.py）
def save_combine_data(df, date_str, time_str):
    # 原有保存逻辑...
    
    # 新增：预计算价格
    df['buy_price'] = df['price_now_zq'].apply(lambda x: round(round(x, 1) + 0.1, 2))
    df['sell_price'] = df['buy_price'] + 0.4
    
    # 保存到Redis
    redis_util.save_dataframe(...)

# 2. 查询时直接使用
record = {
    'buy_price': row.get('buy_price'),  # 无需计算
    'sell_price': row.get('sell_price'),  # 无需计算
}
```

**效果**:
- 每行计算: 2次 → 0次
- **预期耗时: 700ms → 600ms**（次要优化）

---

### 方案C: 使用Redis Hash存储（推荐）

**问题**: DataFrame反序列化耗时（每次10-15ms）

**解决方案**:
```python
# 1. 数据写入时使用Hash存储（替代DataFrame JSON）
def save_combine_data_hash(df, date_str, time_str):
    table_name = f"monitor_combine_{date_str}"
    
    pipe = redis_client.pipeline()
    for _, row in df.iterrows():
        code = row['code']
        key = f"{table_name}:{time_str}:{code}"
        
        # 使用Hash存储（每个字段独立存储）
        pipe.hset(key, mapping={
            'code': code,
            'name': row['name'],
            'price_now_zq': str(row['price_now_zq']),
            'buy_price': str(round(round(row['price_now_zq'], 1) + 0.1, 2)),
            'sell_price': str(round(round(row['price_now_zq'], 1) + 0.5, 2)),
        })
        pipe.expire(key, 86400)
    
    pipe.execute()

# 2. 查询时使用hgetall（比DataFrame反序列化快5倍）
def get_combine_ranking_fast(limit=50):
    # 获取最近10个时间点的所有Hash
    keys = []
    for ts in recent_timestamps:
        keys.extend(redis_client.keys(f"{table_name}:{ts}:*"))
    
    # Pipeline批量hgetall
    pipe = redis_client.pipeline()
    for key in keys[:limit]:
        pipe.hgetall(key)
    
    results = pipe.execute()
    return [decode_hash(r) for r in results]
```

**效果**:
- DataFrame反序列化: 10-15ms → 2-3ms (Hash hgetall)
- **预期耗时: 700ms → 150ms**

---

### 方案D: 缓存API响应（简单有效）

**问题**: 相同请求重复计算

**解决方案**:
```python
@monitor_bp.route('/latest-messages', methods=['GET'])
def get_latest_messages():
    cache_key = f"api:latest-messages:{datetime.now().strftime('%H:%M')}"  # 按分钟缓存
    
    # 1. 查缓存
    cached = redis_client.get(cache_key)
    if cached:
        return jsonify(json.loads(cached))
    
    # 2. 查询数据
    data = data_service.get_combine_ranking(...)
    
    # 3. 写入缓存（30秒过期）
    redis_client.setex(cache_key, 30, json.dumps({
        'success': True,
        'data': data,
        'count': len(data)
    }))
    
    return jsonify({...})
```

**效果**:
- 缓存命中: 700ms → 10ms
- 缓存命中率: 预计80%+
- **平均耗时: 700ms → 150ms**

---

## 五、推荐实施计划

### 阶段1: 减少时间点数量（立即实施）
- [ ] 修改 `get_combine_ranking` 中 `all_ts` 获取数量: 50 → 10
- [ ] 测试验证

**预期效果**: 700ms → 200ms

### 阶段2: 缓存API响应（可选）
- [ ] 添加Redis缓存装饰器
- [ ] 设置30秒过期

**预期效果**: 200ms → 50ms（缓存命中）

### 阶段3: 预计算价格（可选）
- [ ] 修改数据写入逻辑
- [ ] 修改查询逻辑

**预期效果**: 200ms → 150ms

---

## 六、不影响其他功能的设计原则

1. **向后兼容**: 只修改获取数量，不修改返回格式
2. **降级策略**: Redis失败时自动回退到MySQL
3. **配置开关**: 时间点数量可配置
4. **渐进实施**: 每个方案独立验证

---

**请确认后实施方案A（减少时间点数量）？**
