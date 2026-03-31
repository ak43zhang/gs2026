# 非侵入式性能诊断工具设计方案

> 设计时间: 2026-03-31 00:52  
> 目标: 设计三款非侵入式诊断工具，零影响现有业务

---

## 设计原则

| 原则 | 说明 |
|------|------|
| **零侵入** | 不修改现有业务代码 |
| **可插拔** | 随时启用/禁用，不影响功能 |
| **低开销** | 诊断本身不成为性能瓶颈 |
| **独立部署** | 可独立运行，不依赖主服务 |

---

## 工具一：API性能监控中间件（非侵入式）

### 实现方式
使用 Flask 的 `before_request` 和 `after_request` 钩子，不修改任何业务代码。

```python
# gs2026/dashboard2/middleware/performance_monitor.py

import time
import functools
from flask import request, g, jsonify
from loguru import logger
import threading


class PerformanceMonitor:
    """
    API性能监控中间件 - 非侵入式
    
    使用方法:
    1. 在 app.py 中注册: PerformanceMonitor(app)
    2. 或通过环境变量启用: ENABLE_PERF_MONITOR=1
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, app=None, enabled=None):
        if self._initialized:
            return
        
        # 默认通过环境变量控制，未设置时默认为False（非侵入）
        if enabled is None:
            enabled = os.environ.get('ENABLE_PERF_MONITOR', '0') == '1'
        
        self.enabled = enabled
        self.metrics = []
        self.metrics_lock = threading.Lock()
        
        if app:
            self.init_app(app)
        
        self._initialized = True
    
    def init_app(self, app):
        """初始化Flask应用"""
        if not self.enabled:
            logger.info("[PerformanceMonitor] 已禁用，跳过初始化")
            return
        
        @app.before_request
        def before_request():
            g.perf_start_time = time.time()
            g.perf_db_queries = 0
            g.perf_db_time = 0
            g.perf_redis_queries = 0
            g.perf_redis_time = 0
        
        @app.after_request
        def after_request(response):
            if hasattr(g, 'perf_start_time'):
                duration = (time.time() - g.perf_start_time) * 1000
                
                # 记录性能指标
                metric = {
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'method': request.method,
                    'path': request.path,
                    'endpoint': request.endpoint,
                    'duration_ms': round(duration, 2),
                    'status_code': response.status_code,
                    'db_queries': getattr(g, 'perf_db_queries', 0),
                    'db_time_ms': round(getattr(g, 'perf_db_time', 0), 2),
                    'redis_queries': getattr(g, 'perf_redis_queries', 0),
                    'redis_time_ms': round(getattr(g, 'perf_redis_time', 0), 2),
                }
                
                with self.metrics_lock:
                    self.metrics.append(metric)
                    # 只保留最近1000条
                    if len(self.metrics) > 1000:
                        self.metrics = self.metrics[-1000:]
                
                # 慢查询日志（>500ms）
                if duration > 500:
                    logger.warning(
                        f"[SlowAPI] {request.method} {request.path} | "
                        f"{duration:.2f}ms | DB: {metric['db_queries']}q/{metric['db_time_ms']:.2f}ms | "
                        f"Redis: {metric['redis_queries']}q/{metric['redis_time_ms']:.2f}ms"
                    )
                
                # 添加响应头（方便前端查看）
                response.headers['X-Response-Time'] = f"{duration:.2f}ms"
            
            return response
        
        # 注册诊断API（不影响业务API）
        self._register_diag_apis(app)
        
        logger.info("[PerformanceMonitor] 已启用")
    
    def _register_diag_apis(self, app):
        """注册诊断API（独立路由，不影响业务）"""
        
        @app.route('/diag/performance', methods=['GET'])
        def diag_performance():
            """获取性能统计"""
            if not self.enabled:
                return jsonify({'enabled': False})
            
            with self.metrics_lock:
                metrics = self.metrics.copy()
            
            if not metrics:
                return jsonify({'enabled': True, 'message': '暂无数据'})
            
            # 统计计算
            durations = [m['duration_ms'] for m in metrics]
            db_times = [m['db_time_ms'] for m in metrics]
            redis_times = [m['redis_time_ms'] for m in metrics]
            
            return jsonify({
                'enabled': True,
                'total_requests': len(metrics),
                'duration': {
                    'avg': round(sum(durations) / len(durations), 2),
                    'min': round(min(durations), 2),
                    'max': round(max(durations), 2),
                    'p95': round(sorted(durations)[int(len(durations) * 0.95)], 2) if len(durations) > 20 else None,
                },
                'db_time': {
                    'avg': round(sum(db_times) / len(db_times), 2),
                    'total_queries': sum(m['db_queries'] for m in metrics),
                },
                'redis_time': {
                    'avg': round(sum(redis_times) / len(redis_times), 2),
                    'total_queries': sum(m['redis_queries'] for m in metrics),
                },
                'slow_requests': [
                    m for m in sorted(metrics, key=lambda x: -x['duration_ms'])[:10]
                ],
            })
        
        @app.route('/diag/performance/reset', methods=['POST'])
        def diag_performance_reset():
            """重置统计数据"""
            with self.metrics_lock:
                self.metrics = []
            return jsonify({'success': True, 'message': '统计数据已重置'})


# 使用示例（在app.py中）:
# from gs2026.dashboard2.middleware.performance_monitor import PerformanceMonitor
# PerformanceMonitor(app)  # 默认通过环境变量控制
# 或
# PerformanceMonitor(app, enabled=True)  # 强制启用
```

### 启用方式
```bash
# 方式1: 环境变量（推荐）
set ENABLE_PERF_MONITOR=1
python -m gs2026.dashboard2.app

# 方式2: 代码中显式启用
PerformanceMonitor(app, enabled=True)

# 方式3: 默认禁用（完全不加载）
# 不调用 PerformanceMonitor 即可
```

---

## 工具二：数据库查询分析器（非侵入式）

### 实现方式
使用 SQLAlchemy 事件监听，不修改任何查询代码。

```python
# gs2026/dashboard2/middleware/db_profiler.py

import time
from sqlalchemy import event
from loguru import logger
import threading


class DBProfiler:
    """
    数据库查询分析器 - 非侵入式
    
    通过SQLAlchemy事件监听捕获所有查询
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, engine=None, enabled=None, slow_threshold_ms=100):
        if self._initialized:
            return
        
        if enabled is None:
            enabled = os.environ.get('ENABLE_DB_PROFILER', '0') == '1'
        
        self.enabled = enabled
        self.slow_threshold_ms = slow_threshold_ms
        self.queries = []
        self.queries_lock = threading.Lock()
        
        if engine:
            self.attach_to_engine(engine)
        
        self._initialized = True
    
    def attach_to_engine(self, engine):
        """附加到SQLAlchemy引擎"""
        if not self.enabled:
            return
        
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
            context._query_statement = statement[:200]  # 只记录前200字符
        
        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            duration = (time.time() - context._query_start_time) * 1000
            
            query_info = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'statement': context._query_statement,
                'duration_ms': round(duration, 2),
                'parameters': str(parameters)[:100] if parameters else None,
            }
            
            with self.queries_lock:
                self.queries.append(query_info)
                if len(self.queries) > 500:
                    self.queries = self.queries[-500:]
            
            # 慢查询日志
            if duration > self.slow_threshold_ms:
                logger.warning(
                    f"[SlowQuery] {duration:.2f}ms | {context._query_statement[:100]}..."
                )
            
            # 累加到Flask g对象（供PerformanceMonitor使用）
            try:
                from flask import g
                if hasattr(g, 'perf_db_queries'):
                    g.perf_db_queries += 1
                    g.perf_db_time += duration
            except:
                pass
        
        logger.info(f"[DBProfiler] 已附加到引擎，慢查询阈值: {slow_threshold_ms}ms")
    
    def get_stats(self):
        """获取统计信息"""
        if not self.enabled:
            return {'enabled': False}
        
        with self.queries_lock:
            queries = self.queries.copy()
        
        if not queries:
            return {'enabled': True, 'message': '暂无数据'}
        
        durations = [q['duration_ms'] for q in queries]
        
        # 按语句分组统计
        stmt_stats = {}
        for q in queries:
            stmt = q['statement'][:50]  # 简化语句
            if stmt not in stmt_stats:
                stmt_stats[stmt] = {'count': 0, 'total_time': 0, 'max_time': 0}
            stmt_stats[stmt]['count'] += 1
            stmt_stats[stmt]['total_time'] += q['duration_ms']
            stmt_stats[stmt]['max_time'] = max(stmt_stats[stmt]['max_time'], q['duration_ms'])
        
        # 排序找出最慢的语句类型
        slow_stmts = sorted(
            [{'statement': k, **v, 'avg_time': round(v['total_time']/v['count'], 2)} 
             for k, v in stmt_stats.items()],
            key=lambda x: -x['total_time']
        )[:10]
        
        return {
            'enabled': True,
            'total_queries': len(queries),
            'slow_threshold_ms': self.slow_threshold_ms,
            'duration': {
                'avg': round(sum(durations) / len(durations), 2),
                'min': round(min(durations), 2),
                'max': round(max(durations), 2),
                'p95': round(sorted(durations)[int(len(durations) * 0.95)], 2) if len(durations) > 20 else None,
            },
            'slowest_statements': slow_stmts,
            'recent_slow_queries': [
                q for q in sorted(queries, key=lambda x: -x['duration_ms'])[:10]
            ],
        }
    
    def reset(self):
        """重置统计"""
        with self.queries_lock:
            self.queries = []


# 使用示例（在data_service.py中）:
# from gs2026.dashboard2.middleware.db_profiler import DBProfiler
# 
# class DataService:
#     def __init__(self):
#         self.engine = create_engine(...)
#         # 非侵入式附加分析器
#         DBProfiler().attach_to_engine(self.engine)
```

---

## 工具三：前端性能分析器（非侵入式）

### 实现方式
通过独立JS文件引入，不修改现有页面代码。

```javascript
// gs2026/dashboard2/static/js/perf-monitor.js
// 前端性能监控器 - 非侵入式
// 使用方法: 在页面中引入 <script src="/static/js/perf-monitor.js"></script>

(function() {
    'use strict';
    
    // 只在启用时加载
    if (window.DISABLE_PERF_MONITOR) {
        console.log('[PerfMonitor] 已禁用');
        return;
    }
    
    const PerfMonitor = {
        enabled: true,
        metrics: [],
        maxMetrics: 100,
        
        init() {
            this.hookXHR();
            this.hookFetch();
            this.observeResources();
            console.log('[PerfMonitor] 已启用');
        },
        
        // 拦截XMLHttpRequest
        hookXHR() {
            const originalXHR = window.XMLHttpRequest;
            const self = this;
            
            window.XMLHttpRequest = function() {
                const xhr = new originalXHR();
                const startTime = performance.now();
                
                xhr.addEventListener('loadend', function() {
                    const duration = performance.now() - startTime;
                    self.recordMetric({
                        type: 'xhr',
                        url: xhr.responseURL,
                        method: xhr._method || 'GET',
                        duration: Math.round(duration),
                        status: xhr.status,
                        size: xhr.responseText?.length || 0,
                    });
                });
                
                // 保存method
                const originalOpen = xhr.open;
                xhr.open = function(method, url, ...args) {
                    xhr._method = method;
                    xhr._url = url;
                    return originalOpen.apply(this, [method, url, ...args]);
                };
                
                return xhr;
            };
        },
        
        // 拦截Fetch API
        hookFetch() {
            const originalFetch = window.fetch;
            const self = this;
            
            window.fetch = function(...args) {
                const startTime = performance.now();
                const url = args[0];
                const options = args[1] || {};
                
                return originalFetch.apply(this, args).then(response => {
                    const duration = performance.now() - startTime;
                    self.recordMetric({
                        type: 'fetch',
                        url: url,
                        method: options.method || 'GET',
                        duration: Math.round(duration),
                        status: response.status,
                    });
                    return response;
                });
            };
        },
        
        // 观察资源加载
        observeResources() {
            if (!window.PerformanceObserver) return;
            
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.entryType === 'resource') {
                        this.recordMetric({
                            type: 'resource',
                            url: entry.name,
                            duration: Math.round(entry.duration),
                            size: entry.transferSize,
                        });
                    }
                }
            });
            
            observer.observe({ entryTypes: ['resource'] });
        },
        
        // 记录指标
        recordMetric(metric) {
            metric.timestamp = new Date().toISOString();
            this.metrics.push(metric);
            
            if (this.metrics.length > this.maxMetrics) {
                this.metrics.shift();
            }
            
            // 慢请求警告
            if (metric.duration > 500) {
                console.warn(`[SlowRequest] ${metric.url} | ${metric.duration}ms`);
            }
        },
        
        // 获取统计
        getStats() {
            if (this.metrics.length === 0) {
                return { message: '暂无数据' };
            }
            
            const durations = this.metrics.map(m => m.duration);
            const byType = {};
            
            this.metrics.forEach(m => {
                if (!byType[m.type]) {
                    byType[m.type] = { count: 0, total: 0, max: 0 };
                }
                byType[m.type].count++;
                byType[m.type].total += m.duration;
                byType[m.type].max = Math.max(byType[m.type].max, m.duration);
            });
            
            return {
                total: this.metrics.length,
                duration: {
                    avg: Math.round(durations.reduce((a, b) => a + b, 0) / durations.length),
                    min: Math.min(...durations),
                    max: Math.max(...durations),
                },
                byType: Object.entries(byType).map(([type, stats]) => ({
                    type,
                    count: stats.count,
                    avg: Math.round(stats.total / stats.count),
                    max: stats.max,
                })),
                slowest: this.metrics
                    .filter(m => m.duration > 500)
                    .sort((a, b) => b.duration - a.duration)
                    .slice(0, 10),
            };
        },
        
        // 显示面板（可选）
        showPanel() {
            const stats = this.getStats();
            console.table(stats);
            
            // 创建浮动面板
            let panel = document.getElementById('perf-monitor-panel');
            if (!panel) {
                panel = document.createElement('div');
                panel.id = 'perf-monitor-panel';
                panel.style.cssText = `
                    position: fixed;
                    bottom: 10px;
                    right: 10px;
                    background: rgba(0,0,0,0.8);
                    color: #0f0;
                    padding: 10px;
                    border-radius: 5px;
                    font-family: monospace;
                    font-size: 12px;
                    z-index: 9999;
                    max-width: 300px;
                `;
                document.body.appendChild(panel);
            }
            
            panel.innerHTML = `
                <div style="font-weight:bold;margin-bottom:5px;">⚡ 性能监控</div>
                <div>请求数: ${stats.total}</div>
                <div>平均: ${stats.duration?.avg || 0}ms</div>
                <div>最大: ${stats.duration?.max || 0}ms</div>
                <div style="margin-top:5px;font-size:10px;color:#888;">
                    按 F12 → Console 查看详情
                </div>
            `;
        },
    };
    
    // 自动初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => PerfMonitor.init());
    } else {
        PerfMonitor.init();
    }
    
    // 暴露到全局
    window.PerfMonitor = PerfMonitor;
    
    // 快捷键显示面板 (Ctrl+Shift+P)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'P') {
            e.preventDefault();
            PerfMonitor.showPanel();
        }
    });
})();
```

### 使用方式
```html
<!-- 方式1: 在模板中引入（默认启用） -->
<script src="{{ url_for('static', filename='js/perf-monitor.js') }}"></script>

<!-- 方式2: 通过URL参数启用 -->
<!-- monitor.html?perf_monitor=1 -->
<script>
if (new URLSearchParams(window.location.search).get('perf_monitor') === '1') {
    document.write('<script src="/static/js/perf-monitor.js"><\/script>');
}
</script>

<!-- 方式3: 禁用 -->
<script>window.DISABLE_PERF_MONITOR = true;</script>
```

---

## 三款工具对比

| 工具 | 监控层级 | 侵入性 | 启用方式 | 数据存储 |
|------|----------|--------|----------|----------|
| **API性能监控** | 后端 | 零 | 环境变量/代码 | 内存（最近1000条） |
| **数据库分析器** | 数据库 | 零 | 环境变量/代码 | 内存（最近500条） |
| **前端性能分析** | 前端 | 零 | JS引入/URL参数 | 内存（最近100条） |

---

## 集成方案

### 快速启用（推荐）

```bash
# 1. 设置环境变量启用后端诊断
set ENABLE_PERF_MONITOR=1
set ENABLE_DB_PROFILER=1

# 2. 启动服务
python -m gs2026.dashboard2.app

# 3. 前端添加URL参数
# http://localhost:8080/monitor?perf_monitor=1
```

### 诊断API

| 端点 | 说明 |
|------|------|
| `GET /diag/performance` | API性能统计 |
| `POST /diag/performance/reset` | 重置API统计 |
| `GET /diag/db` | 数据库查询统计（需实现） |
| `F12 → Console → PerfMonitor.getStats()` | 前端性能统计 |

---

## 实施计划

### 阶段1: API性能监控（30分钟）
- [ ] 创建 `performance_monitor.py`
- [ ] 在 `app.py` 中注册（默认禁用）
- [ ] 测试验证

### 阶段2: 数据库分析器（30分钟）
- [ ] 创建 `db_profiler.py`
- [ ] 在 `data_service.py` 中附加（默认禁用）
- [ ] 测试验证

### 阶段3: 前端分析器（30分钟）
- [ ] 创建 `perf-monitor.js`
- [ ] 添加到模板（可选引入）
- [ ] 测试验证

### 阶段4: 诊断（持续）
- [ ] 启用诊断工具
- [ ] 收集性能数据
- [ ] 分析瓶颈

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 内存占用增加 | 低 | 低 | 限制存储条数 |
| 轻微性能开销 | 低 | 极低 | 默认禁用，按需启用 |
| 日志量增加 | 中 | 低 | 只记录慢查询 |

---

**三款工具均为非侵入式设计，可随时启用/禁用，不影响现有业务逻辑。**

**请确认是否实施。**
