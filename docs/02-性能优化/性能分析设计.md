# 股票上攻排行性能优化分析方案

> 分析时间: 2026-03-31 00:29  
> 目标: 找出股票上攻排行响应慢的瓶颈，给出优化设计方案

---

## 1. 当前架构分析

### 1.1 数据流图

```
┌─────────────┐     HTTP      ┌──────────────┐     ┌─────────────┐
│   浏览器     │ ─────────────→│  Flask后端   │────→│   MySQL     │
│  (前端)      │   GET /api/   │  (Python)    │     │  (数据存储)  │
└─────────────┘  monitor/...  └──────────────┘     └─────────────┘
                                     │
                                     │ 查询
                                     ↓
                              ┌──────────────┐
                              │    Redis     │
                              │  (缓存层)    │
                              └──────────────┘
```

### 1.2 当前API调用链

```
GET /api/monitor/attack-ranking/stock
  ↓
get_stock_ranking() [monitor.py]
  ↓
data_service.get_stock_ranking() 或 get_ranking_at_time()
  ↓
_process_stock_ranking() [数据加工]
  ↓
  ├─→ get_red_list(date) [Redis查询]
  ├─→ get_stock_bond_mapping(date) [Redis查询]
  └─→ 数据排序、格式化
  ↓
返回JSON
```

---

## 2. 性能瓶颈分析

### 2.1 需要测量的指标

| 指标 | 说明 | 目标值 |
|------|------|--------|
| **TTFB** | 首字节时间 | < 200ms |
| **后端处理时间** | Flask处理耗时 | < 100ms |
| **数据库查询时间** | MySQL查询耗时 | < 50ms |
| **Redis查询时间** | 缓存查询耗时 | < 10ms |
| **数据传输时间** | JSON序列化+传输 | < 50ms |
| **前端渲染时间** | DOM渲染耗时 | < 100ms |

### 2.2 潜在瓶颈点

#### 瓶颈1: MySQL实时查询（最可能）
```python
# 当前实现 - 每次请求都查MySQL
def get_stock_ranking():
    if not time_str:  # 实时查询
        data = data_service.get_stock_ranking(limit=limit, use_mysql=False)
        # use_mysql=False 但Redis为空时会fallback到MySQL
```

**问题**:
- 实时数据可能从MySQL查询
- `monitor_gp_sssj_{date}` 表数据量大
- 无索引或索引未命中

#### 瓶颈2: Redis缓存未命中
```python
# 检查Redis是否有数据
rank_data = redis_client.zrevrange(f"rank:stock:code_{date}", 0, limit-1)
if not rank_data:  # 缓存未命中
    return []  # 或fallback到MySQL
```

**问题**:
- Redis数据可能过期或被清理
- 缓存未命中时无数据返回

#### 瓶颈3: 数据加工逻辑
```python
# _process_stock_ranking 中的循环处理
for item in data:
    # 每个股票都查询红名单和债券映射
    is_red = code in red_list_codes  # Set查找 O(1)
    mapping = stock_bond_mapping.get(code)  # Dict查找 O(1)
```

**问题**:
- 60条数据 × 2次查询 = 120次操作
- 虽然都是O(1)，但有网络开销

#### 瓶颈4: JSON序列化
```python
return jsonify({
    'success': True,
    'data': processed_data,  # 60条数据
    'count': len(processed_data)
})
```

**问题**:
- 60条数据量不大，但字段较多
- Flask默认jsonify可能较慢

#### 瓶颈5: 前端渲染
```javascript
// monitor.html 中的 renderRanking
function renderRanking(data) {
    const html = data.map(item => `
        <tr>...</tr>
    `).join('');
    table.innerHTML = html;  // 60行DOM操作
}
```

**问题**:
- 60行表格一次性插入
- 如果有动画或样式计算会更慢

---

## 3. 诊断工具设计

### 3.1 后端性能分析中间件

```python
# gs2026/dashboard2/middleware/performance.py

import time
import functools
from flask import request, g
from loguru import logger

class PerformanceMonitor:
    """性能监控中间件"""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        @app.before_request
        def before_request():
            g.start_time = time.time()
            g.db_query_count = 0
            g.db_query_time = 0
            g.redis_query_count = 0
            g.redis_query_time = 0
        
        @app.after_request
        def after_request(response):
            if hasattr(g, 'start_time'):
                total_time = (time.time() - g.start_time) * 1000
                
                # 记录性能指标
                logger.info(
                    f"[Performance] {request.method} {request.path} | "
                    f"Total: {total_time:.2f}ms | "
                    f"DB: {g.db_query_count} queries, {g.db_query_time:.2f}ms | "
                    f"Redis: {g.redis_query_count} queries, {g.redis_query_time:.2f}ms | "
                    f"Status: {response.status_code}"
                )
                
                # 添加响应头
                response.headers['X-Response-Time'] = f"{total_time:.2f}ms"
                response.headers['X-DB-Queries'] = str(g.db_query_count)
                response.headers['X-Redis-Queries'] = str(g.redis_query_count)
            
            return response


def timed(func):
    """函数执行时间装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        
        # 累加到全局
        if hasattr(g, 'db_query_time') and 'mysql' in func.__name__:
            g.db_query_count += 1
            g.db_query_time += elapsed
        elif hasattr(g, 'redis_query_time') and 'redis' in func.__name__:
            g.redis_query_count += 1
            g.redis_query_time += elapsed
        
        logger.debug(f"[Timed] {func.__name__}: {elapsed:.2f}ms")
        return result
    return wrapper
```

### 3.2 API性能分析端点

```python
# scheduler.py 中添加诊断API

@scheduler_bp.route('/performance/analyze', methods=['POST'])
def analyze_performance():
    """
    分析指定API的性能瓶颈
    
    Request Body:
    {
        "endpoint": "/api/monitor/attack-ranking/stock",
        "iterations": 10,
        "params": {"limit": 60}
    }
    """
    data = request.get_json()
    endpoint = data.get('endpoint')
    iterations = data.get('iterations', 10)
    params = data.get('params', {})
    
    import requests
    import statistics
    
    times = []
    for i in range(iterations):
        start = time.time()
        response = requests.get(
            f"http://localhost:8080{endpoint}",
            params=params,
            timeout=30
        )
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
    
    return jsonify({
        'success': True,
        'endpoint': endpoint,
        'iterations': iterations,
        'statistics': {
            'min': min(times),
            'max': max(times),
            'avg': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0
        },
        'times': times
    })
```

### 3.3 前端性能分析

```javascript
// monitor.html 中添加性能监控

class PerformanceMonitor {
    constructor() {
        this.metrics = {};
    }
    
    start(label) {
        this.metrics[label] = {
            start: performance.now()
        };
    }
    
    end(label) {
        if (this.metrics[label]) {
            this.metrics[label].end = performance.now();
            this.metrics[label].duration = 
                this.metrics[label].end - this.metrics[label].start;
            console.log(`[Performance] ${label}: ${this.metrics[label].duration.toFixed(2)}ms`);
        }
    }
    
    report() {
        const report = {};
        for (const [label, data] of Object.entries(this.metrics)) {
            if (data.duration) {
                report[label] = data.duration.toFixed(2) + 'ms';
            }
        }
        return report;
    }
}

// 使用示例
const perf = new PerformanceMonitor();

async function loadRanking() {
    perf.start('total');
    
    perf.start('api_request');
    const response = await fetch('/api/monitor/attack-ranking/stock?limit=60');
    perf.end('api_request');
    
    perf.start('json_parse');
    const data = await response.json();
    perf.end('json_parse');
    
    perf.start('render');
    renderRanking(data.data);
    perf.end('render');
    
    perf.end('total');
    
    console.log('Performance Report:', perf.report());
}
```

---

## 4. 优化方案设计

### 方案A: 多级缓存优化（推荐）

```
┌─────────────┐
│  L1: 应用内存缓存  │  ← 最优先，5秒过期
│  (Flask全局变量)  │
├─────────────┤
│  L2: Redis缓存   │  ← 其次，60秒过期
│  (进程间共享)    │
├─────────────┤
│  L3: MySQL查询   │  ← 最后兜底
│  (实时数据)      │
└─────────────┘
```

**实现**:
```python
# 应用内存缓存
from functools import lru_cache
import time

class MemoryCache:
    """应用内存缓存（线程安全）"""
    
    def __init__(self, default_ttl=5):
        self._cache = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
    
    def get(self, key):
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
            return None
    
    def set(self, key, value, ttl=None):
        with self._lock:
            ttl = ttl or self.default_ttl
            self._cache[key] = (value, time.time() + ttl)
    
    def clear(self):
        with self._lock:
            self._cache.clear()

# 全局缓存实例
memory_cache = MemoryCache(default_ttl=5)  # 5秒过期

# 在get_stock_ranking中使用
@scheduler_bp.route('/monitor/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    cache_key = f"stock_ranking:{request.full_path}"
    
    # L1: 内存缓存
    cached = memory_cache.get(cache_key)
    if cached:
        return jsonify(cached)
    
    # L2: Redis缓存
    redis_data = redis_client.get(cache_key)
    if redis_data:
        data = json.loads(redis_data)
        memory_cache.set(cache_key, data)
        return jsonify(data)
    
    # L3: 查询数据库
    result = _get_stock_ranking_from_db()
    
    # 写入缓存
    memory_cache.set(cache_key, result)
    redis_client.setex(cache_key, 60, json.dumps(result))
    
    return jsonify(result)
```

### 方案B: 数据预加载

```python
# 后台定时任务预加载数据到Redis

class DataPreloader:
    """数据预加载服务"""
    
    def __init__(self):
        self.running = False
    
    def start(self):
        """启动预加载服务"""
        self.running = True
        
        # 每5秒预加载股票排行数据
        def preload_stock_ranking():
            while self.running:
                try:
                    data = self._load_stock_ranking()
                    redis_client.setex(
                        'preload:stock_ranking',
                        10,  # 10秒过期
                        json.dumps(data)
                    )
                except Exception as e:
                    logger.error(f"Preload error: {e}")
                
                time.sleep(5)
        
        threading.Thread(target=preload_stock_ranking, daemon=True).start()
    
    def _load_stock_ranking(self):
        """加载股票排行数据"""
        # 查询MySQL获取最新数据
        pass
```

### 方案C: 数据库查询优化

```sql
-- 检查当前索引
SHOW INDEX FROM monitor_gp_sssj_20260330;

-- 添加复合索引（如果缺失）
ALTER TABLE monitor_gp_sssj_20260330 
ADD INDEX idx_code_time (code, time);

-- 添加覆盖索引
ALTER TABLE monitor_gp_sssj_20260330 
ADD INDEX idx_query (date, code, time, price, change_pct);
```

```python
# 优化查询 - 使用批量查询替代循环

# 原实现 - 循环查询（慢）
for code in stock_codes:
    sql = f"SELECT * FROM monitor_gp_sssj_{date} WHERE code = '{code}'"
    result = mysql.query(sql)

# 优化实现 - 批量查询（快）
codes_str = ','.join([f"'{c}'" for c in stock_codes])
sql = f"""
    SELECT code, price, change_pct, time 
    FROM monitor_gp_sssj_{date} 
    WHERE code IN ({codes_str})
    AND time = (SELECT MAX(time) FROM monitor_gp_sssj_{date})
"""
results = mysql.query(sql)
# 转换为字典
price_map = {r['code']: r for r in results}
```

### 方案D: 前端优化

```javascript
// 1. 虚拟滚动（数据量大时）
// 2. 骨架屏优化感知性能
// 3. 增量更新而非全量刷新

// 增量更新示例
function updateRankingIncremental(newData) {
    const table = document.getElementById('ranking-table');
    const rows = table.querySelectorAll('tr');
    
    newData.forEach((item, index) => {
        const row = rows[index + 1]; // +1跳过表头
        if (row) {
            // 只更新变化的单元格
            updateRowCells(row, item);
        }
    });
}
```

---

## 5. 实施建议

### 第一阶段: 诊断（1天）
1. 部署性能监控中间件
2. 添加API性能分析端点
3. 收集实际性能数据
4. 确定瓶颈所在

### 第二阶段: 优化（2天）
根据诊断结果选择优化方案：
- 如果MySQL慢 → 方案C（索引优化）+ 方案A（缓存）
- 如果Redis慢 → 方案A（多级缓存）
- 如果前端慢 → 方案D（前端优化）
- 如果都慢 → 组合方案

### 第三阶段: 验证（1天）
1. 对比优化前后性能
2. 确保业务逻辑不受影响
3. 监控线上性能指标

---

## 6. 预期效果

| 优化项 | 当前 | 目标 | 提升 |
|--------|------|------|------|
| API响应时间 | ?ms | < 100ms | ?x |
| 数据库查询 | ?ms | < 20ms | ?x |
| 前端渲染 | ?ms | < 50ms | ?x |

**注意**: 需要先部署诊断工具收集实际数据，才能给出准确的优化效果预估。

---

**下一步**: 部署诊断工具收集性能数据，确定瓶颈后再实施优化。
