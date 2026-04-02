# 性能监控工具使用指南

> 文档时间: 2026-03-31 08:30  
> 说明: 三个性能监控工具的启用方式和使用方法

---

## 配置位置

所有配置在 `configs/settings.yaml` 中：

```yaml
# 性能诊断工具配置
performance_monitor:
    enabled: false              # API性能监控开关
    slow_threshold_ms: 500      # 慢请求阈值
    max_metrics: 1000           # 最大保留指标数
    log_slow_requests: true     # 记录慢请求

db_profiler:
    enabled: false              # 数据库分析器开关
    slow_threshold_ms: 100      # 慢查询阈值
    max_queries: 500            # 最大保留查询数
    log_slow_queries: true      # 记录慢查询

frontend_perf:
    enabled: false              # 前端性能监控开关
    max_metrics: 100            # 最大保留指标数
    show_panel_shortcut: true   # 快捷键显示面板
```

---

## 工具一：API性能监控

### 启用方式

**方法1: settings.yaml（推荐）**
```yaml
performance_monitor:
    enabled: true
```

**方法2: 环境变量（优先级更高）**
```bash
set ENABLE_PERF_MONITOR=1
```

### 使用方式

**1. 查看性能统计**
```
GET http://localhost:8080/diag/performance
```

返回示例：
```json
{
    "enabled": true,
    "total_requests": 150,
    "duration": {
        "avg": 45.2,
        "min": 12.1,
        "max": 523.4,
        "p95": 89.5
    },
    "db_time": {
        "avg": 15.3,
        "total_queries": 320
    },
    "redis_time": {
        "avg": 8.2,
        "total_queries": 280
    },
    "slow_requests": [
        {"path": "/api/monitor/attack-ranking/stock", "duration_ms": 523.4, ...}
    ]
}
```

**2. 重置统计**
```
POST http://localhost:8080/diag/performance/reset
```

**3. 查看响应头**
每个API响应都包含：
```
X-Response-Time: 45.23ms
```

**4. 日志查看**
慢请求（>500ms）自动记录到日志：
```
[SlowAPI] GET /api/monitor/attack-ranking/stock | 523.40ms | DB: 2q/15.30ms | Redis: 3q/8.20ms
```

---

## 工具二：数据库分析器

### 启用方式

**方法1: settings.yaml（推荐）**
```yaml
db_profiler:
    enabled: true
```

**方法2: 环境变量（优先级更高）**
```bash
set ENABLE_DB_PROFILER=1
```

### 使用方式

**1. 查看数据库统计**
```
GET http://localhost:8080/diag/db
```

返回示例：
```json
{
    "enabled": true,
    "total_queries": 450,
    "slow_threshold_ms": 100,
    "duration": {
        "avg": 25.3,
        "min": 5.1,
        "max": 234.5,
        "p95": 65.2
    },
    "slowest_statements": [
        {"statement": "SELECT * FROM monitor_gp_top30...", "count": 50, "avg_time": 45.2}
    ],
    "recent_slow_queries": [
        {"statement": "SELECT...", "duration_ms": 234.5, ...}
    ]
}
```

**2. 重置统计**
```
POST http://localhost:8080/diag/db/reset
```

**3. 日志查看**
慢查询（>100ms）自动记录到日志：
```
[SlowQuery] 234.50ms | SELECT * FROM monitor_gp_top30_20260330 WHERE...
```

---

## 工具三：前端性能监控

### 启用方式

**方法1: settings.yaml（默认启用）**
```yaml
frontend_perf:
    enabled: true
```

**方法2: URL参数（临时启用）**
```
http://localhost:8080/monitor?perf_monitor=1
```

**方法3: 全局变量（禁用）**
```javascript
window.DISABLE_PERF_MONITOR = true;
```

### 使用方式

**1. 查看控制台输出**
打开浏览器开发者工具（F12）→ Console：
```
[PerfMonitor] 已启用（按 Ctrl+Shift+P 显示面板）
```

**2. 显示监控面板**
快捷键：`Ctrl + Shift + P`

或控制台执行：
```javascript
PerfMonitor.showPanel();
```

**3. 获取统计数据**
```javascript
PerfMonitor.getStats();
```

返回示例：
```javascript
{
    total: 45,
    duration: {avg: 120, min: 45, max: 560},
    byType: [
        {type: 'xhr', count: 30, avg: 110, max: 450},
        {type: 'fetch', count: 10, avg: 150, max: 560},
        {type: 'resource', count: 5, avg: 80, max: 200}
    ],
    slowest: [
        {url: '/api/monitor/attack-ranking/stock', duration: 560, type: 'fetch'}
    ]
}
```

**4. 面板显示**
页面右下角显示浮动面板：
```
⚡ 性能监控
请求数: 45
平均: 120ms
最大: 560ms
按 F12 → Console 查看详情
```

---

## 快速启用所有工具

### 步骤1: 修改 settings.yaml
```yaml
performance_monitor:
    enabled: true

db_profiler:
    enabled: true

frontend_perf:
    enabled: true
```

### 步骤2: 重启Flask服务
```bash
python -m gs2026.dashboard2.app
```

### 步骤3: 查看启动日志
```
[PerfMonitor] API性能监控: 已启用
[PerfMonitor] 数据库分析器: 已启用
[PerfMonitor] 前端性能监控: 已启用
```

### 步骤4: 访问监控页面
```
http://localhost:8080/monitor
```

### 步骤5: 查看性能数据
- 后端API: `http://localhost:8080/diag/performance`
- 数据库: `http://localhost:8080/diag/db`
- 前端: 按 `Ctrl+Shift+P` 显示面板

---

## 配置参数说明

### performance_monitor
| 参数 | 说明 | 默认值 |
|------|------|--------|
| enabled | 是否启用 | false |
| slow_threshold_ms | 慢请求阈值（毫秒） | 500 |
| max_metrics | 最大保留请求数 | 1000 |
| log_slow_requests | 是否记录慢请求 | true |

### db_profiler
| 参数 | 说明 | 默认值 |
|------|------|--------|
| enabled | 是否启用 | false |
| slow_threshold_ms | 慢查询阈值（毫秒） | 100 |
| max_queries | 最大保留查询数 | 500 |
| log_slow_queries | 是否记录慢查询 | true |

### frontend_perf
| 参数 | 说明 | 默认值 |
|------|------|--------|
| enabled | 是否默认启用 | false |
| max_metrics | 最大保留请求数 | 100 |
| show_panel_shortcut | 是否启用快捷键 | true |

---

## 故障排查

### 问题1: 诊断API返回404
**原因**: 中间件未启用  
**解决**: 检查 settings.yaml 中 enabled: true

### 问题2: 前端面板不显示
**原因**: 前端监控未启用  
**解决**: 
- 方法1: settings.yaml 中设置 enabled: true
- 方法2: URL添加 `?perf_monitor=1`

### 问题3: 统计数据为空
**原因**: 还没有请求  
**解决**: 先访问几个页面产生数据

### 问题4: 内存占用过高
**原因**: 保留数据过多  
**解决**: 降低 max_metrics / max_queries 配置

---

## 生产环境建议

```yaml
# 生产环境配置
performance_monitor:
    enabled: true
    slow_threshold_ms: 1000      # 提高阈值，减少日志
    max_metrics: 500             # 减少内存占用
    log_slow_requests: true

db_profiler:
    enabled: true
    slow_threshold_ms: 500       # 提高阈值
    max_queries: 300
    log_slow_queries: true

frontend_perf:
    enabled: false               # 生产环境默认禁用
    max_metrics: 50
    show_panel_shortcut: false   # 禁用快捷键
```

---

**文档位置**: `docs/performance_monitor_usage.md`
