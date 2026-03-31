# 慢查询/慢请求持久化存储设计方案

> 设计时间: 2026-03-31 09:09  
> 目标: 设计数据表存储慢查询和慢请求记录，用于后续分析

---

## 一、需求分析

### 1.1 存储需求

| 类型 | 说明 | 存储内容 |
|------|------|----------|
| **慢请求** | API响应时间超过阈值 | 请求方法、路径、耗时、DB查询数、Redis查询数 |
| **慢查询** | SQL执行时间超过阈值 | SQL语句、执行时间、参数 |
| **前端慢资源** | 前端资源加载时间超过阈值 | 资源类型、URL、耗时、大小 |

### 1.2 分析需求

- **趋势分析**: 慢请求/查询数量随时间变化
- **热点分析**: 哪些API/SQL最慢、最频繁
- **告警**: 慢请求/查询数量突增时通知
- **报表**: 按天/周/月统计

---

## 二、数据库表设计

### 2.1 慢请求表 (slow_requests)

```sql
CREATE TABLE slow_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    request_date DATE NOT NULL COMMENT '请求日期',
    request_hour TINYINT NOT NULL COMMENT '请求小时(0-23)',
    
    -- 请求信息
    method VARCHAR(10) NOT NULL COMMENT 'HTTP方法(GET/POST/...)',
    path VARCHAR(500) NOT NULL COMMENT '请求路径',
    endpoint VARCHAR(200) COMMENT '端点名称',
    
    -- 性能指标
    duration_ms INT NOT NULL COMMENT '总耗时(毫秒)',
    status_code SMALLINT COMMENT 'HTTP状态码',
    
    -- 数据库指标
    db_queries INT DEFAULT 0 COMMENT '数据库查询次数',
    db_time_ms INT DEFAULT 0 COMMENT '数据库耗时(毫秒)',
    
    -- Redis指标
    redis_queries INT DEFAULT 0 COMMENT 'Redis查询次数',
    redis_time_ms INT DEFAULT 0 COMMENT 'Redis耗时(毫秒)',
    
    -- 扩展信息(JSON格式，可选)
    extra_info JSON COMMENT '扩展信息',
    
    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_request_date (request_date),
    INDEX idx_path (path(100)),
    INDEX idx_duration (duration_ms),
    INDEX idx_composite (request_date, duration_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='慢请求记录表';
```

### 2.2 慢查询表 (slow_queries)

```sql
CREATE TABLE slow_queries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    query_date DATE NOT NULL COMMENT '查询日期',
    query_hour TINYINT NOT NULL COMMENT '查询小时(0-23)',
    
    -- SQL信息
    sql_statement TEXT NOT NULL COMMENT 'SQL语句(前500字符)',
    sql_hash VARCHAR(64) COMMENT 'SQL语句MD5哈希(用于归类相同SQL)',
    sql_type VARCHAR(20) COMMENT 'SQL类型(SELECT/INSERT/UPDATE/DELETE)',
    
    -- 性能指标
    duration_ms INT NOT NULL COMMENT '执行耗时(毫秒)',
    
    -- 表信息(从SQL解析)
    table_name VARCHAR(100) COMMENT '主表名',
    
    -- 参数信息(可选)
    parameters TEXT COMMENT 'SQL参数(前200字符)',
    
    -- 扩展信息
    extra_info JSON COMMENT '扩展信息',
    
    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_query_date (query_date),
    INDEX idx_sql_hash (sql_hash),
    INDEX idx_duration (duration_ms),
    INDEX idx_table_name (table_name),
    INDEX idx_composite (query_date, duration_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='慢查询记录表';

### 2.3 前端慢资源表 (slow_frontend_resources)

```sql
CREATE TABLE slow_frontend_resources (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 时间信息
    created_at DATETIME NOT NULL COMMENT '记录创建时间',
    resource_date DATE NOT NULL COMMENT '资源加载日期',
    resource_hour TINYINT NOT NULL COMMENT '资源加载小时(0-23)',
    
    -- 资源信息
    resource_type VARCHAR(20) NOT NULL COMMENT '资源类型(xhr/fetch/script/css/image/other)',
    url VARCHAR(1000) NOT NULL COMMENT '资源URL',
    url_path VARCHAR(500) COMMENT 'URL路径(用于归类)',
    
    -- 性能指标
    duration_ms INT NOT NULL COMMENT '加载耗时(毫秒)',
    transfer_size BIGINT COMMENT '传输大小(字节)',
    
    -- 页面信息
    page_url VARCHAR(500) COMMENT '所在页面URL',
    
    -- 扩展信息
    extra_info JSON COMMENT '扩展信息(如HTTP状态码、缓存状态等)',
    
    -- 索引
    INDEX idx_created_at (created_at),
    INDEX idx_resource_date (resource_date),
    INDEX idx_resource_type (resource_type),
    INDEX idx_url_path (url_path(100)),
    INDEX idx_duration (duration_ms),
    INDEX idx_composite (resource_date, resource_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='前端慢资源加载记录表';
```

### 2.4 表结构说明

| 表名 | 用途 | 预估数据量 |
|------|------|-----------|
| slow_requests | 存储慢API请求 | 每天100-1000条 |
| slow_queries | 存储慢SQL查询 | 每天1000-10000条 |
| slow_frontend_resources | 存储前端慢资源 | 每天500-5000条 |

---

## 三、后端实现设计

### 3.1 数据模型 (models/slow_log.py)

```python
"""
慢查询/慢请求数据模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Date, Integer, String, Text, SmallINT, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SlowRequest(Base):
    """慢请求记录"""
    __tablename__ = 'slow_requests'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    request_date = Column(Date, nullable=False)
    request_hour = Column(Integer, nullable=False)
    
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    endpoint = Column(String(200))
    
    duration_ms = Column(Integer, nullable=False)
    status_code = Column(SmallINT)
    
    db_queries = Column(Integer, default=0)
    db_time_ms = Column(Integer, default=0)
    redis_queries = Column(Integer, default=0)
    redis_time_ms = Column(Integer, default=0)
    
    extra_info = Column(JSON)


class SlowQuery(Base):
    """慢查询记录"""
    __tablename__ = 'slow_queries'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    query_date = Column(Date, nullable=False)
    query_hour = Column(Integer, nullable=False)
    
    sql_statement = Column(Text, nullable=False)
    sql_hash = Column(String(64))
    sql_type = Column(String(20))
    
    duration_ms = Column(Integer, nullable=False)
    table_name = Column(String(100))
    parameters = Column(Text)
    
    extra_info = Column(JSON)


class SlowFrontendResource(Base):
    """前端慢资源加载记录"""
    __tablename__ = 'slow_frontend_resources'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    resource_date = Column(Date, nullable=False)
    resource_hour = Column(Integer, nullable=False)
    
    resource_type = Column(String(20), nullable=False)
    url = Column(String(1000), nullable=False)
    url_path = Column(String(500))
    
    duration_ms = Column(Integer, nullable=False)
    transfer_size = Column(BigInteger)
    
    page_url = Column(String(500))
    
    extra_info = Column(JSON)
```

### 3.2 存储服务 (services/slow_log_service.py)

```python
"""
慢查询/慢请求存储服务
"""
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gs2026.models.slow_log import Base, SlowRequest, SlowQuery, SlowFrontendResource


class SlowLogService:
    """慢日志存储服务"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: str = None):
        if self._initialized:
            return
        
        if db_url is None:
            from gs2026.dashboard.config import Config
            db_url = Config().SQLALCHEMY_DATABASE_URI
        
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)  # 自动创建表
        self.Session = sessionmaker(bind=self.engine)
        self._initialized = True
    
    def save_slow_request(self, data: dict) -> bool:
        """
        保存慢请求记录
        
        Args:
            data: {
                'method': 'GET',
                'path': '/api/monitor/...',
                'endpoint': 'get_stock_ranking',
                'duration_ms': 523,
                'status_code': 200,
                'db_queries': 5,
                'db_time_ms': 150,
                'redis_queries': 3,
                'redis_time_ms': 45,
                'extra_info': {...}
            }
        """
        try:
            now = datetime.now()
            
            record = SlowRequest(
                created_at=now,
                request_date=now.date(),
                request_hour=now.hour,
                method=data.get('method', ''),
                path=data.get('path', '')[:500],
                endpoint=data.get('endpoint', '')[:200],
                duration_ms=data.get('duration_ms', 0),
                status_code=data.get('status_code'),
                db_queries=data.get('db_queries', 0),
                db_time_ms=data.get('db_time_ms', 0),
                redis_queries=data.get('redis_queries', 0),
                redis_time_ms=data.get('redis_time_ms', 0),
                extra_info=data.get('extra_info')
            )
            
            session = self.Session()
            session.add(record)
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            print(f"保存慢请求失败: {e}")
            return False
    
    def save_slow_query(self, data: dict) -> bool:
        """
        保存慢查询记录
        
        Args:
            data: {
                'sql_statement': 'SELECT * FROM ...',
                'duration_ms': 234,
                'parameters': '(param1, param2)',
                'extra_info': {...}
            }
        """
        try:
            now = datetime.now()
            sql = data.get('sql_statement', '')
            
            # 计算SQL哈希
            sql_hash = hashlib.md5(sql.encode()).hexdigest()
            
            # 解析SQL类型
            sql_type = self._parse_sql_type(sql)
            
            # 解析表名
            table_name = self._parse_table_name(sql)
            
            record = SlowQuery(
                created_at=now,
                query_date=now.date(),
                query_hour=now.hour,
                sql_statement=sql[:500],  # 只存前500字符
                sql_hash=sql_hash,
                sql_type=sql_type,
                duration_ms=data.get('duration_ms', 0),
                table_name=table_name,
                parameters=str(data.get('parameters', ''))[:200],
                extra_info=data.get('extra_info')
            )
            
            session = self.Session()
            session.add(record)
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            print(f"保存慢查询失败: {e}")
            return False
    
    def _parse_sql_type(self, sql: str) -> str:
        """解析SQL类型"""
        sql_upper = sql.strip().upper()
        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        return 'OTHER'
    
    def _parse_table_name(self, sql: str) -> Optional[str]:
        """简单解析主表名"""
        try:
            sql_upper = sql.upper()
            if 'FROM' in sql_upper:
                parts = sql_upper.split('FROM')[1].strip().split()
                if parts:
                    return parts[0].strip('`"[]')
        except:
            pass
        return None
    
    def get_stats(self, date: str = None) -> dict:
        """获取统计信息"""
        from sqlalchemy import func
        
        session = self.Session()
        
        try:
            # 慢请求统计
            req_query = session.query(
                func.count(SlowRequest.id).label('total'),
                func.avg(SlowRequest.duration_ms).label('avg_duration'),
                func.max(SlowRequest.duration_ms).label('max_duration')
            )
            
            if date:
                req_query = req_query.filter(SlowRequest.request_date == date)
            
            req_stats = req_query.first()
            
            # 慢查询统计
            query_query = session.query(
                func.count(SlowQuery.id).label('total'),
                func.avg(SlowQuery.duration_ms).label('avg_duration'),
                func.max(SlowQuery.duration_ms).label('max_duration')
            )
            
            if date:
                query_query = query_query.filter(SlowQuery.query_date == date)
            
            query_stats = query_query.first()
            
            # 前端慢资源统计
            fe_query = session.query(
                func.count(SlowFrontendResource.id).label('total'),
                func.avg(SlowFrontendResource.duration_ms).label('avg_duration'),
                func.max(SlowFrontendResource.duration_ms).label('max_duration')
            )
            
            if date:
                fe_query = fe_query.filter(SlowFrontendResource.resource_date == date)
            
            fe_stats = fe_query.first()
            
            return {
                'slow_requests': {
                    'total': req_stats.total or 0,
                    'avg_duration': round(req_stats.avg_duration or 0, 2),
                    'max_duration': req_stats.max_duration or 0
                },
                'slow_queries': {
                    'total': query_stats.total or 0,
                    'avg_duration': round(query_stats.avg_duration or 0, 2),
                    'max_duration': query_stats.max_duration or 0
                },
                'slow_frontend': {
                    'total': fe_stats.total or 0,
                    'avg_duration': round(fe_stats.avg_duration or 0, 2),
                    'max_duration': fe_stats.max_duration or 0
                }
            }
            
        finally:
            session.close()
    
    def save_slow_frontend_resource(self, data: dict) -> bool:
        """
        保存前端慢资源加载记录
        
        Args:
            data: {
                'resource_type': 'xhr',
                'url': 'http://localhost:8080/api/...',
                'duration_ms': 1200,
                'transfer_size': 1024,
                'page_url': 'http://localhost:8080/monitor',
                'extra_info': {...}
            }
        """
        try:
            now = datetime.now()
            url = data.get('url', '')
            
            # 提取URL路径
            url_path = self._extract_url_path(url)
            
            record = SlowFrontendResource(
                created_at=now,
                resource_date=now.date(),
                resource_hour=now.hour,
                resource_type=data.get('resource_type', 'other'),
                url=url[:1000],
                url_path=url_path[:500],
                duration_ms=data.get('duration_ms', 0),
                transfer_size=data.get('transfer_size'),
                page_url=data.get('page_url', '')[:500],
                extra_info=data.get('extra_info')
            )
            
            session = self.Session()
            session.add(record)
            session.commit()
            session.close()
            return True
            
        except Exception as e:
            print(f"保存前端慢资源失败: {e}")
            return False
    
    def _extract_url_path(self, url: str) -> str:
        """从URL提取路径部分"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.path
        except:
            return url[:200]
```

### 3.3 修改中间件集成存储

**修改 performance_monitor.py:**

```python
# 在 after_request 中，慢请求时保存到数据库
if duration > self.slow_threshold_ms:
    # 记录日志
    logger.warning(...)
    
    # 保存到数据库（异步，不阻塞响应）
    try:
        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        SlowLogService().save_slow_request({
            'method': request.method,
            'path': request.path,
            'endpoint': request.endpoint,
            'duration_ms': round(duration, 2),
            'status_code': response.status_code,
            'db_queries': metric['db_queries'],
            'db_time_ms': metric['db_time_ms'],
            'redis_queries': metric['redis_queries'],
            'redis_time_ms': metric['redis_time_ms']
        })
    except:
        pass  # 保存失败不影响主流程
```

**修改 db_profiler.py:**

```python
# 在 after_cursor_execute 中，慢查询时保存到数据库
if duration > self.slow_threshold_ms:
    # 记录日志
    logger.warning(...)
    
    # 保存到数据库
    try:
        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        SlowLogService().save_slow_query({
            'sql_statement': context._query_statement,
            'duration_ms': round(duration, 2),
            'parameters': parameters
        })
    except:
        pass
```

**前端性能监控上报 (performance.js):**

```javascript
// 在 initFrontendMonitor 中，慢资源时上报到后端
if (duration > 1000) {  // 超过1秒认为是慢资源
    fetch('/api/performance/slow-frontend', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            resource_type: 'xhr',
            url: xhr.responseURL,
            duration_ms: Math.round(duration),
            page_url: window.location.href
        }),
        keepalive: true  // 页面关闭时也能发送
    }).catch(() => {});  // 忽略错误
}
```

**后端接收API (routes/performance.py):**

```python
@performance_bp.route('/api/performance/slow-frontend', methods=['POST'])
def report_slow_frontend():
    """接收前端慢资源上报"""
    try:
        data = request.get_json()
        SlowLogService().save_slow_frontend_resource(data)
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 500
```

---

## 四、前端展示增强

### 4.1 性能监控页面增加历史统计

在 performance.html 中增加：

```html
<!-- 历史统计卡片 -->
<div class="history-stats">
    <h3>📈 今日慢请求/查询/前端资源统计</h3>
    <div class="stats-grid">
        <div class="stat-item">
            <span class="stat-value" id="today-slow-req">-</span>
            <span class="stat-label">慢请求数</span>
        </div>
        <div class="stat-item">
            <span class="stat-value" id="today-slow-query">-</span>
            <span class="stat-label">慢查询数</span>
        </div>
        <div class="stat-item">
            <span class="stat-value" id="today-slow-fe">-</span>
            <span class="stat-label">慢前端资源</span>
        </div>
    </div>
</div>

<!-- 热点分析 -->
<div class="hotspot-analysis">
    <h3>🔥 热点分析（近7天）</h3>
    <div class="hotspot-tabs">
        <button class="hotspot-tab active" data-type="api">慢API</button>
        <button class="hotspot-tab" data-type="sql">慢SQL</button>
        <button class="hotspot-tab" data-type="frontend">慢前端资源</button>
    </div>
    <table id="hotspot-table">
        <!-- 最慢的API/SQL/前端资源 -->
    </table>
</div>
```

### 4.2 新增API端点

```python
@performance_bp.route('/api/performance/slow-stats')
def get_slow_stats():
    """获取慢请求/查询统计"""
    date = request.args.get('date')
    stats = SlowLogService().get_stats(date)
    return jsonify(stats)

@performance_bp.route('/api/performance/hotspot')
def get_hotspot():
    """获取热点分析（最慢的API/SQL）"""
    days = request.args.get('days', 7, type=int)
    # 查询近N天最频繁的慢请求/查询
    ...
```

---

## 五、实施计划

### 阶段1: 数据库表创建（20分钟）
- [ ] 创建 `slow_requests` 表
- [ ] 创建 `slow_queries` 表
- [ ] 创建 `slow_frontend_resources` 表

### 阶段2: 后端实现（60分钟）
- [ ] 创建 `models/slow_log.py` 数据模型（3个表）
- [ ] 创建 `services/slow_log_service.py` 存储服务（含前端方法）
- [ ] 修改 `performance_monitor.py` 集成存储
- [ ] 修改 `db_profiler.py` 集成存储
- [ ] 修改 `data_service.py` 附加分析器（修复禁用问题）
- [ ] 创建 `routes/performance.py` 接收前端上报

### 阶段3: 前端增强（40分钟）
- [ ] 修改 `performance.html` 增加历史统计（含前端资源）
- [ ] 修改 `performance.js` 加载历史数据+上报慢资源
- [ ] 新增API端点（含前端资源热点）

### 阶段4: 测试验证（20分钟）
- [ ] 验证慢请求存储
- [ ] 验证慢查询存储
- [ ] 验证前端慢资源存储
- [ ] 验证前端展示

**总计: 140分钟**

---

## 六、数据清理策略

```sql
-- 每天凌晨清理30天前的数据
DELETE FROM slow_requests WHERE request_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY);
DELETE FROM slow_queries WHERE query_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY);
DELETE FROM slow_frontend_resources WHERE resource_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY);
```

或在Python中实现定时清理任务。

---

**文档位置**: `docs/slow_log_storage_design.md`

**请确认方案后实施。**
