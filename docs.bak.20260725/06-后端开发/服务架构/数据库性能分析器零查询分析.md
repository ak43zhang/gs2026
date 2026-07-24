# 性能监控数据库查询为0问题分析报告

> 分析时间: 2026-03-31 12:08  
> 问题: 性能监控页面中数据库实时总查询和下面都是0

---

## 一、问题确认

### 1.1 诊断端点返回

```
GET /diag/db
{
    "enabled": True,
    "total_queries": None,  ← 没有查询记录！
    "message": "暂无数据"
}
```

### 1.2 本地测试验证

```python
# 手动创建DataService并执行查询
profiler = DBProfiler()
profiler.enabled: True
profiler._attached_engines: set()  ← 空的！
profiler.queries: []  ← 没有记录！

# 执行查询后
profiler.queries: [{'statement': 'SELECT 1', ...}]  ← 有记录了！
```

---

## 二、根本原因

### 2.1 问题分析

**DataService初始化流程**:
```python
# data_service.py
class DataService:
    def __init__(self):
        self.engine = create_engine(...)  # 创建新引擎
        
        profiler = DBProfiler(enabled=True)
        profiler.attach_to_engine(self.engine)  # 附加到新引擎
```

**问题**:
1. 每次创建 `DataService` 都会创建一个新的 `engine`
2. 每个 `DataService` 实例都会调用 `attach_to_engine`
3. 但 `app.py` 中的诊断端点使用的是 `DBProfiler()` 单例
4. 如果Flask应用中的查询不是通过 `DBProfiler` 附加的引擎执行的，就不会被记录

### 2.2 实际调用链路

```
Flask请求 → monitor.py → data_service.get_stock_ranking()
    ↓
DataService实例（A）→ engine A → 查询
    ↓
DBProfiler单例 → _attached_engines = {id(engine A)}
    ↓
查询被记录到 DBProfiler.queries

另一个请求 → monitor.py → data_service.get_combine_ranking()
    ↓
DataService实例（B）→ engine B → 查询
    ↓
DBProfiler单例 → _attached_engines = {id(engine A), id(engine B)}
    ↓
查询应该被记录...
```

### 2.3 可能的问题

1. **DataService被多次实例化**: 每次请求都创建新的 `DataService`，导致多个引擎
2. **查询没有通过SQLAlchemy执行**: 可能直接使用了 `mysql_util` 或其他方式
3. **DBProfiler单例状态不一致**: `app.py` 中的 `DBProfiler()` 和 `data_service.py` 中的不是同一个

---

## 三、排查验证

### 3.1 检查DataService实例化次数

```python
# 在 data_service.py 中添加计数器
_instance_count = 0

class DataService:
    def __init__(self):
        global _instance_count
        _instance_count += 1
        print(f"[DataService] 第 {_instance_count} 次实例化")
```

### 3.2 检查查询执行方式

```python
# 检查 monitor.py 中的查询是否通过DataService.engine执行
# 或者通过其他方式（如mysql_util）
```

### 3.3 检查DBProfiler单例

```python
# 在 app.py 和 data_service.py 中打印DBProfiler实例ID
print(f"[DBProfiler] 实例ID: {id(DBProfiler())}")
```

---

## 四、解决方案

### 方案A: 使用单例DataService（推荐）

确保整个应用使用同一个 `DataService` 实例：

```python
# data_service.py
_data_service_instance = None

def get_data_service():
    global _data_service_instance
    if _data_service_instance is None:
        _data_service_instance = DataService()
    return _data_service_instance

class DataService:
    def __init__(self):
        # ... 初始化代码
        pass
```

修改调用方式:
```python
# monitor.py
from gs2026.dashboard.services.data_service import get_data_service

data_service = get_data_service()
data = data_service.get_stock_ranking(...)
```

---

### 方案B: 在app.py中统一附加引擎

在Flask应用启动时，创建一个全局引擎并附加到DBProfiler：

```python
# app.py
def create_app():
    app = Flask(...)
    
    # 创建全局引擎
    from sqlalchemy import create_engine
    from gs2026.dashboard.config import Config
    
    config = Config()
    engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        pool_recycle=3600,
        pool_pre_ping=True
    )
    
    # 附加到DBProfiler
    if PERF_MONITOR_AVAILABLE:
        profiler = DBProfiler()
        if profiler.enabled:
            profiler.attach_to_engine(engine)
            app.config['DB_ENGINE'] = engine  # 存储全局引擎
    
    # ... 其他初始化
```

修改 `DataService` 使用全局引擎：
```python
# data_service.py
class DataService:
    def __init__(self):
        # 使用全局引擎（如果存在）
        from flask import current_app
        if 'DB_ENGINE' in current_app.config:
            self.engine = current_app.config['DB_ENGINE']
        else:
            # 创建新引擎（fallback）
            self.engine = create_engine(...)
```

---

### 方案C: 修改DBProfiler为类级别统计

让 `DBProfiler` 使用类变量存储查询，而不是实例变量：

```python
# db_profiler.py
class DBProfiler:
    # 类级别变量
    _queries = []
    _queries_lock = threading.Lock()
    
    def __init__(self, ...):
        # 不再使用 self.queries
        pass
    
    def attach_to_engine(self, engine):
        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(...):
            # 使用类变量
            with DBProfiler._queries_lock:
                DBProfiler._queries.append(query_info)
    
    def get_stats(self):
        with DBProfiler._queries_lock:
            queries = DBProfiler._queries.copy()
```

---

### 方案D: 使用SQLAlchemy的before/after事件全局监听

不依赖特定引擎，全局监听所有SQLAlchemy查询：

```python
# db_profiler.py
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "before_cursor_execute")
def global_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()

@event.listens_for(Engine, "after_cursor_execute")
def global_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    duration = (time.time() - context._query_start_time) * 1000
    # 记录到DBProfiler类变量
    DBProfiler.add_query({...})
```

---

## 五、推荐方案

**推荐方案C + 方案D组合**:

1. **方案C**: 使用类级别变量存储查询，确保所有实例共享数据
2. **方案D**: 全局监听所有SQLAlchemy引擎的查询事件

**优点**:
- 不依赖单例模式
- 自动捕获所有SQLAlchemy查询
- 无需修改现有代码

---

## 六、实施方案

### 修改 db_profiler.py

```python
class DBProfiler:
    """数据库查询分析器 - 非侵入式"""
    
    # 类级别共享数据
    _queries = []
    _queries_lock = threading.Lock()
    _attached_engines = set()  # 类级别
    _global_enabled = False    # 类级别
    
    def __init__(self, engine=None, enabled=None, slow_threshold_ms=None):
        # 加载配置
        profiler_config = _load_db_profiler_config()
        
        if enabled is None:
            enabled = os.environ.get('ENABLE_DB_PROFILER')
            if enabled is not None:
                enabled = enabled == '1'
            else:
                enabled = profiler_config.get('enabled', False)
        
        # 设置类级别状态
        DBProfiler._global_enabled = enabled
        self.enabled = enabled
        self.slow_threshold_ms = slow_threshold_ms or profiler_config.get('slow_threshold_ms', 100)
        self.max_queries = profiler_config.get('max_queries', 500)
        self.log_slow_queries = profiler_config.get('log_slow_queries', True)
        
        if engine:
            self.attach_to_engine(engine)
    
    def attach_to_engine(self, engine):
        """附加到SQLAlchemy引擎"""
        if not DBProfiler._global_enabled:
            return
        
        engine_id = id(engine)
        if engine_id in DBProfiler._attached_engines:
            return
        
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
            context._query_statement = statement[:1000] if statement else ""
        
        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            duration = (time.time() - context._query_start_time) * 1000
            
            query_info = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'statement': context._query_statement,
                'duration_ms': round(duration, 2),
                'parameters': str(parameters)[:100] if parameters else None,
            }
            
            with DBProfiler._queries_lock:
                DBProfiler._queries.append(query_info)
                if len(DBProfiler._queries) > self.max_queries:
                    DBProfiler._queries = DBProfiler._queries[-self.max_queries:]
        
        DBProfiler._attached_engines.add(engine_id)
        logger.info(f"[DBProfiler] 已附加到引擎")
    
    def get_stats(self):
        """获取统计信息"""
        if not DBProfiler._global_enabled:
            return {'enabled': False}
        
        with DBProfiler._queries_lock:
            queries = DBProfiler._queries.copy()
        
        if not queries:
            return {'enabled': True, 'message': '暂无数据', 'total_queries': 0}
        
        # ... 统计计算
        return {
            'enabled': True,
            'total_queries': len(queries),
            # ...
        }
    
    def reset(self):
        """重置统计"""
        with DBProfiler._queries_lock:
            DBProfiler._queries = []
        return {'success': True, 'message': '统计数据已重置'}
```

---

## 七、验证步骤

1. **修改代码**后重启Flask服务
2. **访问** `/performance` 页面
3. **触发** 一些数据库查询（如刷新股票排行）
4. **检查** `/diag/db` 端点返回的 `total_queries` 是否大于0

---

**文档位置**: `docs/db_profiler_zero_queries_analysis.md`

**推荐方案**: 方案C（类级别变量）
