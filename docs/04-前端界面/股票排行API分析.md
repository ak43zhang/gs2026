# /api/monitor/attack-ranking/stock 接口深度分析报告

> 分析时间: 2026-03-31 19:23  
> 接口: GET /api/monitor/attack-ranking/stock?limit=60

---

## 一、性能数据

### 1.1 历史慢请求统计

| 时间 | 总耗时 | DB查询 | DB时间 | 其他时间 |
|------|--------|--------|--------|----------|
| 19:04:56 | 747.0ms | 1次 | 73.8ms | **673.2ms** |
| 18:25:35 | 672.2ms | 1次 | 230.4ms | **441.8ms** |
| 18:25:56 | 610.4ms | 1次 | 58.8ms | **551.5ms** |
| 18:25:54 | 597.4ms | 1次 | 42.9ms | **554.5ms** |

**关键发现**:
- **DB时间仅占10-30%**（42-230ms）
- **其他时间占70-90%**（441-673ms）
- 其他时间 = Python处理 + 数据enrichment + JSON序列化

### 1.2 实时测试

| 参数 | 返回条数 | 总耗时 |
|------|----------|--------|
| limit=60 | 60条 | **2132ms** |
| limit=30 | 30条 | **2076ms** |
| limit=10 | 10条 | **2093ms** |

**关键发现**:
- limit参数**几乎不影响**总耗时
- 说明耗时主要在**固定开销**，而非数据处理

---

## 二、完整调用链分析

### 2.1 调用链图

```
GET /api/monitor/attack-ranking/stock?limit=60
    ↓ ~2100ms 总耗时
Flask路由处理
    ↓ ~50ms
monitor_bp.route('/attack-ranking/stock')
    ↓
get_stock_ranking()
    ↓
data_service.get_stock_ranking(limit=60)
    ↓ ~100-300ms
get_rising_ranking(asset_type='stock')
    ├── 1. 查Redis (优先)
    │   └── zrevrange + hget (快，<50ms)
    └── 2. Redis未命中，查MySQL
        └── SELECT ... FROM monitor_gp_top30_{date} (100-300ms)
    ↓
_process_stock_ranking(data)  ← 【主要耗时点】
    ├── _enrich_stock_data(data)      ← ~200-400ms
    │   └── cache.get_mapping() x 60  ← Redis查询 x 60
    ├── _enrich_change_pct(data)      ← ~200-400ms
    │   └── load_dataframe_by_key()   ← Redis查询
    └── 红名单标记                     ← ~50ms
        └── get_red_list()            ← Redis查询
    ↓
jsonify() + 网络传输                ← ~100-200ms
```

### 2.2 各阶段耗时估算

| 阶段 | 耗时 | 占比 | 说明 |
|------|------|------|------|
| Flask路由 | ~50ms | 2% | 请求解析、路由匹配 |
| 数据查询 | ~100-300ms | 10-15% | Redis/MySQL查询 |
| **_enrich_stock_data** | **~200-400ms** | **15-20%** | 60次Redis查询 |
| **_enrich_change_pct** | **~200-400ms** | **15-20%** | DataFrame处理 |
| 红名单标记 | ~50ms | 2% | Redis查询 |
| JSON序列化 | ~100-200ms | 5-10% | 60条数据序列化 |
| **其他开销** | **~800-1200ms** | **40-60%** | Python处理、GC等 |

---

## 三、根本原因分析

### 3.1 主要原因: `_enrich_stock_data` 循环查询

**代码位置**: `monitor.py:62-85`

```python
def _enrich_stock_data(stocks: list) -> list:
    cache = get_cache()
    
    for stock in stocks:  # ← 循环60次
        stock_code = stock.get('code', '')
        mapping = cache.get_mapping(stock_code)  # ← 每次Redis查询
        
        if mapping:
            stock['bond_code'] = mapping.get('bond_code', '-')
            stock['bond_name'] = mapping.get('bond_name', '-')
            stock['industry_name'] = mapping.get('industry_name', '-')
```

**问题**:
- 60只股票 × 1次Redis查询 = **60次网络往返**
- 每次Redis查询 ~5-10ms
- 总计: **300-600ms**

### 3.2 次要原因: `_enrich_change_pct` DataFrame处理

**代码位置**: `monitor.py:102-180`

```python
def _enrich_change_pct(stocks: list, date: str, time_str: str = None) -> list:
    # 1. 从Redis获取DataFrame
    df = redis_util.load_dataframe_by_key(redis_key)
    
    # 2. 遍历DataFrame构建映射
    change_pct_map = {}
    for _, row in df.iterrows():  # ← 遍历240行
        code = str(row.get('code', '')).zfill(6)
        change_pct_map[code] = float(change_pct)
    
    # 3. 为每只股票匹配
    for stock in stocks:  # ← 遍历60只
        stock['change_pct'] = change_pct_map.get(code)
```

**问题**:
- DataFrame遍历和匹配耗时
- 预计: **200-400ms**

### 3.3 其他开销

**JSON序列化**:
- 60条数据，每条约20个字段
- 预计: **100-200ms**

**Python处理开销**:
- 函数调用、内存分配、GC等
- 预计: **800-1200ms**

---

## 四、优化方案

### 方案A: 批量获取股票映射（推荐）

**问题**: 60次循环查询 → 1次批量查询

**解决方案**:
```python
# 1. 添加批量查询方法到 StockBondMappingCache
def get_mappings_batch(self, stock_codes: list) -> dict:
    """批量获取股票映射"""
    today = datetime.now().strftime('%Y-%m-%d')
    mapping_key = f"{REDIS_KEY_PREFIX}:{today}"
    
    pipe = self.redis_client.pipeline()
    for code in stock_codes:
        pipe.hget(mapping_key, code)
    
    results = pipe.execute()
    
    mappings = {}
    for code, data in zip(stock_codes, results):
        if data:
            mappings[code] = json.loads(data)
    
    return mappings

# 2. 修改 _enrich_stock_data
def _enrich_stock_data(stocks: list) -> list:
    cache = get_cache()
    
    # 批量获取所有映射（1次Redis查询）
    codes = [s['code'] for s in stocks]
    mappings = cache.get_mappings_batch(codes)
    
    # 填充数据
    for stock in stocks:
        mapping = mappings.get(stock['code'], {})
        stock['bond_code'] = mapping.get('bond_code', '-')
        stock['bond_name'] = mapping.get('bond_name', '-')
        stock['industry_name'] = mapping.get('industry_name', '-')
    
    return stocks
```

**预期效果**:
- Redis查询: 60次 → 1次
- 耗时: 400ms → 50ms
- 总耗时: 2100ms → 1200ms

---

### 方案B: 预计算并缓存 enrichment 结果

**问题**: 每次请求都重新计算 enrichment

**解决方案**:
```python
# 1. 在数据写入时预计算
def save_dataframe(...):
    # 原有保存逻辑...
    
    # 新增：预计算 enrichment 数据
    if 'top30' in table_name:
        _precompute_enrichment(df, table_name, time_str)

def _precompute_enrichment(df, table_name, time_str):
    """预计算 enrichment 数据并缓存"""
    cache = get_cache()
    
    for _, row in df.iterrows():
        code = row['code']
        mapping = cache.get_mapping(code)
        
        # 构建 enriched 数据
        enriched = {
            'code': code,
            'name': row['name'],
            'count': row['count'],
            'bond_code': mapping.get('bond_code', '-'),
            'bond_name': mapping.get('bond_name', '-'),
            'industry_name': mapping.get('industry_name', '-'),
            'change_pct': row.get('change_pct_now'),
        }
        
        # 缓存到Redis
        redis_key = f"enriched:{table_name}:{time_str}:{code}"
        redis_client.setex(redis_key, 3600, json.dumps(enriched))

# 2. 查询时直接使用缓存
def get_stock_ranking(...):
    # 获取基础排行数据
    ranking = data_service.get_stock_ranking(...)
    
    # 从缓存获取 enrichment 数据
    enriched_data = []
    for item in ranking:
        redis_key = f"enriched:monitor_gp_top30_{date}:{time_str}:{item['code']}"
        cached = redis_client.get(redis_key)
        if cached:
            enriched_data.append(json.loads(cached))
    
    return enriched_data
```

**预期效果**:
- enrichment 耗时: 600ms → 50ms
- 总耗时: 2100ms → 600ms

---

### 方案C: 异步 enrichment（前端分步加载）

**问题**: 等待所有数据 enrichment 完成才返回

**解决方案**:
```python
@monitor_bp.route('/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    # 1. 快速返回核心数据
    core_data = data_service.get_stock_ranking_core(limit=limit, date=date)
    
    # 2. 启动后台任务 enrichment（通过Celery或线程）
    # 或使用WebSocket推送 enrichment 数据
    
    return jsonify({
        'success': True,
        'data': core_data,  # 只包含 code, name, count
        'enriched': False,
        'message': 'enrichment数据加载中...'
    })

# 前端分两次请求
# 第一次: 获取核心数据（快速）
# 第二次: 获取 enrichment 数据（异步）
```

**预期效果**:
- 首屏响应: 2100ms → 300ms
- 用户体验: 渐进式加载

---

### 方案D: 使用 Pipeline 批量查询涨跌幅

**问题**: `_enrich_change_pct` DataFrame处理耗时

**解决方案**:
```python
def _enrich_change_pct(stocks: list, date: str, time_str: str = None) -> list:
    if not stocks:
        return stocks
    
    # 1. 批量获取涨跌幅（使用Pipeline）
    codes = [s['code'] for s in stocks]
    
    # 构建Redis key
    table_name = f"monitor_gp_top30_{date}"
    if not time_str:
        # 获取最新时间
        ts_key = f"{table_name}:timestamps"
        latest_ts = redis_client.lindex(ts_key, 0)
        time_str = latest_ts.decode() if latest_ts else None
    
    if not time_str:
        return stocks
    
    # 2. 一次性获取DataFrame
    redis_key = f"{table_name}:{time_str}"
    df = redis_util.load_dataframe_by_key(redis_key)
    
    if df is None or df.empty:
        return stocks
    
    # 3. 使用向量化操作（替代循环）
    code_list = [str(c).zfill(6) for c in df['code'].values]
    change_pct_list = df['change_pct_now'].values if 'change_pct_now' in df.columns else df['change_pct'].values
    
    # 4. 构建字典（更快）
    change_pct_map = dict(zip(code_list, change_pct_list))
    
    # 5. 批量填充
    for stock in stocks:
        stock['change_pct'] = change_pct_map.get(stock['code'].zfill(6))
    
    return stocks
```

**预期效果**:
- 涨跌幅 enrichment: 300ms → 100ms

---

## 五、推荐实施计划

### 阶段1: 批量获取股票映射（立即实施）
- [ ] 在 `stock_bond_mapping_cache.py` 添加 `get_mappings_batch()`
- [ ] 修改 `_enrich_stock_data()` 使用批量查询
- [ ] 测试验证

**预期效果**: 2100ms → 1200ms

### 阶段2: 优化涨跌幅 enrichment（可选）
- [ ] 优化 `_enrich_change_pct()` 使用向量化操作
- [ ] 测试验证

**预期效果**: 1200ms → 900ms

### 阶段3: 预计算缓存（可选）
- [ ] 在数据写入时预计算 enrichment
- [ ] 修改查询逻辑使用缓存
- [ ] 测试验证

**预期效果**: 900ms → 500ms

---

## 六、不影响其他功能的设计原则

1. **向后兼容**: 所有修改保持API接口不变
2. **降级策略**: Redis失败时自动回退到原逻辑
3. **配置开关**: 批量查询可通过配置启用/禁用
4. **渐进实施**: 每个方案独立，可单独验证

---

**请确认后实施方案A（批量获取股票映射）？**
