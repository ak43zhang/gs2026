# API性能深度分析报告

> 分析时间: 2026-03-31 19:14  
> 数据来源: 性能监控诊断端点

---

## 一、慢请求统计

### 1.1 整体情况

| 指标 | 数值 |
|------|------|
| 总请求数 | 1000 |
| 慢请求数 | 10 |
| 平均响应 | 145.93ms |
| P95响应 | 498.67ms |

### 1.2 慢请求列表（按耗时排序）

| 排名 | 端点 | 路径 | 耗时 | DB查询 | DB时间 | Redis时间 |
|------|------|------|------|--------|--------|-----------|
| 1 | `monitor.get_chart_data` | `/api/monitor/chart-data/123160/300992` | **3645.92ms** | 2 | 3081.4ms | 0 |
| 2 | `monitor.get_chart_data` | `/api/monitor/chart-data/123259/300763` | **3442.85ms** | 2 | 2906.28ms | 0 |
| 3 | `monitor.get_stock_ranking` | `/api/monitor/attack-ranking/stock` | 804.14ms | 1 | 761.26ms | 0 |
| 4 | `monitor.get_stock_ranking` | `/api/monitor/attack-ranking/stock` | 747.0ms | 1 | 73.8ms | 0 |
| 5 | `monitor.get_latest_messages` | `/api/monitor/latest-messages` | 729.05ms | 0 | 0 | 0 |
| 6 | `monitor.get_latest_messages` | `/api/monitor/latest-messages` | 704.12ms | 0 | 0 | 0 |
| 7 | `monitor.get_stock_ranking` | `/api/monitor/attack-ranking/stock` | 672.2ms | 1 | 230.38ms | 0 |
| 8 | `performance.get_slow_stats` | `/api/performance/slow-stats` | 625.65ms | 0 | 0 | 0 |
| 9 | `performance.get_slow_stats` | `/api/performance/slow-stats` | 618.64ms | 0 | 0 | 0 |
| 10 | `monitor.get_stock_ranking` | `/api/monitor/attack-ranking/stock` | 610.37ms | 1 | 58.84ms | 0 |

---

## 二、关键发现

### 2.1 最慢端点: `monitor.get_chart_data`

**问题**: 平均耗时 **3544ms**，最大 **3645ms**

**调用链分析**:
```
GET /api/monitor/chart-data/{bond_code}/{stock_code}
    ↓ 3645ms 总耗时
monitor.py::get_chart_data()
    ↓
data_service.py::get_chart_data()
    ├── 查询债券分时数据 (MySQL)
    │   └── SELECT * FROM monitor_zq_sssj_20260331 WHERE bond_code = '123160'
    │       └── 耗时: ~1500ms
    └── 查询正股分时数据 (MySQL)
        └── SELECT * FROM monitor_gp_sssj_20260331 WHERE stock_code = '300992'
            └── 耗时: ~1500ms
```

**根本原因**:
- 虽然已添加索引，但查询返回**所有历史数据**（无LIMIT限制）
- 单只股票一天有4800条记录，查询返回全部
- 数据序列化和传输耗时

### 2.2 次要慢端点: `monitor.get_stock_ranking`

**问题**: 平均耗时 **708ms**

**调用链分析**:
```
GET /api/monitor/attack-ranking/stock
    ↓ 708ms 总耗时
monitor.py::get_stock_ranking()
    ↓
data_service.py::get_stock_ranking() / get_ranking_at_time()
    ↓
_process_stock_ranking()
    ├── _enrich_stock_data()      ← 债券/行业信息
    │   └── cache.get_mapping()   ← Redis查询（快）
    ├── _enrich_change_pct()      ← 涨跌幅
    │   └── Redis查询（快）
    └── 红名单标记
        └── get_red_list()        ← Redis查询（快）
```

**根本原因**:
- 数据服务层查询耗时
- `_enrich_change_pct` 需要查询Redis获取涨跌幅
- 部分请求DB时间高达761ms（可能涉及历史数据回退）

### 2.3 数据库慢查询

**最慢查询**:
```sql
-- 27秒（索引添加前）
SELECT time, stock_code, short_name, price, change_pct, volume, amount
FROM monitor_gp_sssj_20260331
WHERE stock_code = '300992'
ORDER BY time ASC
```

**当前状态**: 索引已添加，但查询仍返回全部数据

---

## 三、优化方案设计

### 方案A: 限制 chart_data 返回数据量（推荐）

**问题**: `get_chart_data` 返回全天4800条数据

**解决方案**:
```python
# data_service.py::get_chart_data()

# 修改前: 返回所有数据
query = f"""
    SELECT time, stock_code, short_name, price, change_pct, volume, amount
    FROM {stock_table}
    WHERE stock_code = '{stock_code}'
    ORDER BY time ASC
"""

# 修改后: 只返回最近100条（或按时间间隔采样）
query = f"""
    SELECT time, stock_code, short_name, price, change_pct, volume, amount
    FROM {stock_table}
    WHERE stock_code = '{stock_code}'
    ORDER BY time DESC
    LIMIT 100
"""

# 或按时间间隔采样（每5分钟一条）
query = f"""
    SELECT time, stock_code, short_name, price, change_pct, volume, amount
    FROM {stock_table}
    WHERE stock_code = '{stock_code}'
    AND time IN (
        SELECT DISTINCT time 
        FROM {stock_table} 
        WHERE stock_code = '{stock_code}'
        AND time REGEXP ':(00|05|10|15|20|25|30|35|40|45|50|55):00$'
    )
    ORDER BY time ASC
"""
```

**预期效果**:
- 数据量: 4800条 → 100条（或96条/5分钟采样）
- 响应时间: 3645ms → 200-500ms
- 不影响其他功能

---

### 方案B: 缓存 chart_data 数据

**问题**: 相同股票/债券的chart数据被重复查询

**解决方案**:
```python
# 添加Redis缓存
def get_chart_data(self, bond_code, stock_code, date=None):
    if date is None:
        date = self.get_latest_date()
    
    # 构建缓存key
    cache_key = f"chart:{bond_code}:{stock_code}:{date}"
    
    # 1. 先查Redis缓存
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # 2. 查询MySQL
    result = self._query_chart_data_from_mysql(bond_code, stock_code, date)
    
    # 3. 写入缓存（5分钟过期）
    redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
```

**预期效果**:
- 首次查询: 3645ms
- 缓存命中: 10-50ms
- 缓存命中率: 预计80%+

---

### 方案C: 优化 get_stock_ranking 数据流

**问题**: `_enrich_change_pct` 每次都查询Redis

**解决方案**:
```python
# 方案1: 批量获取涨跌幅
def _enrich_change_pct_batch(self, stocks, date, time_str):
    """批量获取涨跌幅，减少Redis查询"""
    codes = [s['code'] for s in stocks]
    
    # 使用Pipeline批量查询
    pipe = redis_client.pipeline()
    for code in codes:
        pipe.hget(f"change_pct:{date}:{time_str}", code)
    
    results = pipe.execute()
    
    for stock, change_pct in zip(stocks, results):
        stock['change_pct'] = float(change_pct) if change_pct else None

# 方案2: 预加载涨跌幅数据
def get_stock_ranking(self, limit=60, date=None, use_mysql=False):
    # 先获取排行数据
    ranking = self._get_ranking_from_redis(limit, date)
    
    # 预加载所有需要的涨跌幅数据（一次查询）
    change_pct_map = self._preload_change_pct(date, ranking)
    
    # 填充数据
    for item in ranking:
        item['change_pct'] = change_pct_map.get(item['code'])
    
    return ranking
```

**预期效果**:
- Redis查询: N次 → 1次
- 响应时间: 708ms → 400-500ms

---

### 方案D: 异步加载非关键数据

**问题**: 股票排行需要等待所有数据 enrichment 完成

**解决方案**:
```python
# 前端优先显示核心数据，非关键数据异步加载
@monitor_bp.route('/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    # 1. 快速返回核心数据（代码、名称、次数）
    core_data = data_service.get_stock_ranking_core(limit=limit, date=date)
    
    # 2. 启动后台任务 enrichment
    # 债券/行业信息、涨跌幅等通过WebSocket推送或下次请求返回
    
    return jsonify({
        'success': True,
        'data': core_data,  # 快速返回
        'enriched': False   # 标记未完全 enrichment
    })

# 或前端分两次请求
# 第一次: 获取核心排行数据
# 第二次: 获取 enrichment 数据（债券/行业/涨跌幅）
```

**预期效果**:
- 首屏响应: 708ms → 100-200ms
- 用户体验: 渐进式加载

---

## 四、推荐实施计划

### 阶段1: 限制 chart_data 数据量（立即实施）
- [ ] 修改 `get_chart_data` 添加 LIMIT 100
- [ ] 测试响应时间
- **预期**: 3645ms → 500ms

### 阶段2: 添加 chart_data 缓存（可选）
- [ ] 实现Redis缓存
- [ ] 设置5分钟过期
- **预期**: 缓存命中时 50ms

### 阶段3: 优化 get_stock_ranking（可选）
- [ ] 批量获取涨跌幅
- [ ] 预加载优化
- **预期**: 708ms → 400ms

---

## 五、不影响其他功能的设计原则

1. **只读优化**: 所有优化都是查询层面的，不影响写入
2. **降级策略**: 缓存失败时自动回退到原查询
3. **配置开关**: 所有优化可通过配置启用/禁用
4. **渐进实施**: 每个方案独立，可单独验证

---

**请确认后实施方案A（限制 chart_data 数据量）？**
