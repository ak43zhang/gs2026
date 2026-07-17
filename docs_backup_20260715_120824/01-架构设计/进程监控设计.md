# 进程监控系统设计文档

## 1. 设计目标

### 1.1 核心需求
- 实时监控 Dashboard 启动的后台进程
- 自动检测进程异常停止
- 提供统一的进程状态查询接口
- 支持进程状态变更通知

### 1.2 设计原则
- **无侵入性**：不影响现有代码逻辑
- **高可靠性**：Redis 持久化 + 多线程监控
- **可扩展性**：支持任意数量进程
- **向后兼容**：原有接口完全保持不变

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard (Flask)                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │              ProcessManager                      │   │
│  │  ┌─────────────┐    ┌─────────────────────────┐ │   │
│  │  │ 原有业务逻辑 │───▶│ ProcessManagerWithMonitor│ │   │
│  │  │ (保持不变)  │    │    (适配器层)            │ │   │
│  │  └─────────────┘    └───────────┬─────────────┘ │   │
│  │                                  │               │   │
│  │  ┌───────────────────────────────▼─────────────┐ │   │
│  │  │         ProcessMonitor (核心监控)           │ │   │
│  │  │  - 进程注册/注销                            │ │   │
│  │  │  - 心跳检测 (10秒)                          │ │   │
│  │  │  - 状态变更检测                             │ │   │
│  │  │  - 回调通知                                 │ │   │
│  │  └───────────────────────┬─────────────────────┘ │   │
│  └──────────────────────────┼───────────────────────┘   │
└─────────────────────────────┼───────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────┐
│                      Redis 存储                          │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ process:{id}    │  │ heartbeat:{id}  │              │
│  │ - pid           │  │ - timestamp     │              │
│  │ - status        │  │ - status        │              │
│  │ - start_time    │  └─────────────────┘              │
│  │ - process_type  │                                   │
│  │ - meta          │  ┌─────────────────┐              │
│  └─────────────────┘  │ process:registry│              │
│                       │ (所有进程集合)   │              │
│                       └─────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

### 2.2 数据模型

#### ProcessInfo (进程信息)
```python
@dataclass
class ProcessInfo:
    process_id: str      # 唯一标识
    pid: int             # 系统PID
    status: str          # running/stopped/error/unknown
    start_time: str      # ISO格式
    last_heartbeat: str  # ISO格式
    process_type: str    # 进程类型
    meta: Dict           # 额外元数据
```

#### Redis Key 设计
| Key | 类型 | 说明 |
|-----|------|------|
| `process:{id}` | String | 进程信息(JSON) |
| `process:heartbeat:{id}` | String | 心跳数据 |
| `process:{id}:auto_restart` | String | 自动重启标记 |
| `process:registry` | Set | 所有进程ID集合 |

---

## 3. 核心组件

### 3.1 ProcessMonitor (监控核心)

**文件**: `src/gs2026/utils/process_monitor.py`

**职责**:
- 进程注册/注销
- 心跳更新
- 状态查询
- 监控线程管理

**关键方法**:
```python
# 注册进程
register(process_id, pid, process_type, meta, auto_restart)

# 注销进程
unregister(process_id)

# 更新心跳
update_heartbeat(process_id, status, extra_data)

# 获取状态
get_status(process_id) -> ProcessInfo

# 启动监控线程
start_monitoring()

# 停止监控线程
stop_monitoring()

# 注册状态变更回调
on_status_change(process_id, callback)
```

**监控逻辑**:
```python
def _check_processes(self):
    for info in all_processes:
        # 检查系统进程是否存在
        is_alive = psutil.Process(info.pid).is_running()
        
        if not is_alive and info.status == "running":
            # 进程停止，更新状态
            update_status(process_id, "stopped")
            trigger_callback(process_id, "stopped", info)
            
            # 检查自动重启
            if auto_restart_enabled:
                trigger_callback(process_id, "auto_restart", info)
```

### 3.2 ProcessManagerWithMonitor (适配器)

**文件**: `src/gs2026/dashboard/services/process_monitor_adapter.py`

**职责**:
- 保持 ProcessManager 原有接口
- 自动注册/注销进程
- 状态变更回调处理

**集成方式**:
```python
class ProcessManager(ProcessManagerWithMonitor):
    # 原有代码无需修改
    pass
```

**自动注册点**:
- `start_collection()` → 注册 `collection`
- `start_analysis()` → 注册 `analysis`
- `start_monitor()` → 注册 `monitor`
- `start_service()` → 注册 `service:{id}`
- `start_analysis_service()` → 注册 `analysis:{id}`

**自动注销点**:
- `_stop_process()` → 注销对应进程
- `stop_service()` → 注销 `service:{id}`
- `stop_analysis_service()` → 注销 `analysis:{id}`

---

## 4. 接口设计

### 4.1 内部接口

#### 进程注册
```python
POST /internal/register
{
    "process_id": "collection",
    "pid": 12345,
    "process_type": "collection",
    "meta": {"dates": ["20260325"]}
}
```

#### 状态查询
```python
GET /internal/status/{process_id}
Response: {
    "process_id": "collection",
    "pid": 12345,
    "status": "running",
    "is_running": true,
    "start_time": "2025-03-25T10:00:00",
    "last_heartbeat": "2025-03-25T10:05:00"
}
```

### 4.2 外部 API

#### 获取所有监控进程状态
```http
GET /api/control/monitor-status

Response:
{
    "success": true,
    "data": [
        {
            "process_id": "collection",
            "pid": 12345,
            "status": "running",
            "is_running": true,
            "process_type": "collection",
            "start_time": "2025-03-25T10:00:00",
            "last_heartbeat": "2025-03-25T10:05:00"
        }
    ],
    "count": 1
}
```

---

## 5. 配置参数

### 5.1 监控参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| check_interval | 10秒 | 检查间隔 |
| heartbeat_timeout | 30秒 | 心跳超时 |

### 5.2 进程类型
| 类型 | 说明 |
|------|------|
| collection | 数据采集 |
| analysis | AI分析 |
| monitor | 监控程序 |
| monitor_service | 独立监控服务 |
| analysis_service | 独立分析服务 |

---

## 6. 使用示例

### 6.1 基本使用
```python
from gs2026.utils.process_monitor import get_process_monitor

monitor = get_process_monitor()

# 注册进程
monitor.register(
    process_id='my_service',
    pid=12345,
    process_type='service',
    meta={'key': 'value'}
)

# 启动监控
monitor.start_monitoring()

# 查询状态
status = monitor.get_status('my_service')
print(status.status)  # running

# 停止监控
monitor.stop_monitoring()
```

### 6.2 状态变更回调
```python
def on_status_change(process_id, status, info):
    print(f"{process_id} -> {status}")
    if status == "stopped":
        # 发送通知
        send_alert(f"进程 {process_id} 已停止")

monitor.on_status_change("my_service", on_status_change)
```

### 6.3 Dashboard 集成
```python
# ProcessManager 自动集成
pm = ProcessManager()

# 启动服务（自动注册监控）
pm.start_service('stock_monitor', 'monitor_stock.py')

# 查询监控状态
status = pm.get_process_status('service:stock_monitor')
```

---

## 7. 测试方案

### 7.1 单元测试
```bash
python -m gs2026.tests.test_process_monitor
```

测试内容：
1. 注册/注销
2. 状态查询
3. 自动检测停止
4. 回调功能

### 7.2 集成测试
1. 启动 Dashboard
2. 启动一个服务
3. 查看监控状态
4. 手动停止进程
5. 验证状态变更

### 7.3 数据查看
```bash
python -m gs2026.tools.view_process_monitor
```

---

## 8. 注意事项

### 8.1 性能考虑
- 监控线程为守护线程，不阻塞主程序
- 检查间隔可配置，默认10秒
- Redis 连接使用连接池

### 8.2 异常处理
- 进程不存在时自动标记为 stopped
- Redis 连接失败不影响业务逻辑
- 所有异常均有日志记录

### 8.3 清理策略
- 提供 `cleanup_stopped()` 方法清理历史数据
- 默认保留24小时内的停止记录

---

## 9. 未来扩展

### 9.1 计划功能
- [ ] 自动重启策略
- [ ] 进程资源监控（CPU/内存）
- [ ] 进程日志聚合
- [ ] WebSocket 实时推送状态

### 9.2 优化方向
- [ ] 支持分布式监控
- [ ] 监控数据持久化到数据库
- [ ] 可视化监控面板
