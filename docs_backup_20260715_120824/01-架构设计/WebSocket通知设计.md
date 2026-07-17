# WebSocket 实时通知系统设计文档

## 1. 设计目标

### 1.1 核心需求
- 实时推送股债联动新信号到前端
- 浏览器语音播报（中文）
- 页面弹窗通知
- 最小化代码侵入

### 1.2 设计原则
- **独立性**: 独立应用（app_ws.py），不影响原有 app.py
- **可选性**: WebSocket 为可选功能，不强制使用
- **兼容性**: 原有功能完全不受影响

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                   浏览器 (前端)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Socket.IO Client                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │   │
│  │  │ 实时信号接收 │  │ 语音播报    │  │ 弹窗通知│ │   │
│  │  │ (new_signal)│  │(Speech API) │  │ (Toast) │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────┘ │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │ WebSocket
┌─────────────────────────▼───────────────────────────────┐
│              Dashboard WebSocket 服务                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Flask-SocketIO                      │   │
│  │  ┌─────────────┐  ┌─────────────────────────┐  │   │
│  │  │ 连接管理    │  │ 事件处理                │  │   │
│  │  │ (connect)   │  │  - new_signal           │  │   │
│  │  │ (disconnect)│  │  - connection_status    │  │   │
│  │  └─────────────┘  └─────────────────────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │ 调用
┌─────────────────────────▼───────────────────────────────┐
│              股债联动监控程序                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │     monitor_gp_zq_rising_signal.py              │   │
│  │                                                 │   │
│  │  检测到新信号 ──▶ notify_new_signal(data)       │   │
│  │                      │                          │   │
│  │                      ▼                          │   │
│  │              WebSocket 推送                     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
1. 监控程序检测到新信号
   ↓
2. 调用 notify_new_signal(data)
   ↓
3. SocketIO 广播到所有连接客户端
   ↓
4. 前端接收 new_signal 事件
   ↓
5. 触发：弹窗 + 语音播报 + 数据刷新
```

---

## 3. 核心组件

### 3.1 WebSocket 服务端

**文件**: `src/gs2026/dashboard/app_ws.py`

**职责**:
- 提供 WebSocket 服务
- 管理客户端连接
- 处理信号推送

**关键代码**:
```python
from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    emit('connection_status', {'status': 'connected'})

def notify_new_signal(data):
    """推送新信号到所有客户端"""
    socketio.emit('new_signal', data)
```

**启动方式**:
```bash
python -m gs2026.dashboard.app_ws
# 端口: 5000
```

### 3.2 WebSocket 通知工具

**文件**: `src/gs2026/utils/websocket_notifier.py`

**职责**:
- 封装通知逻辑
- 支持可选依赖

**关键代码**:
```python
try:
    from flask import current_app
    def notify_new_signal(data):
        if 'socketio' in current_app.extensions:
            current_app.extensions['socketio'].emit('new_signal', data)
except ImportError:
    def notify_new_signal(data):
        pass  # WebSocket 未启用
```

### 3.3 前端客户端

**文件**: `src/gs2026/dashboard/templates/monitor_ws.html`

**职责**:
- Socket.IO 连接
- 信号处理
- 语音播报
- 弹窗显示

**关键代码**:
```javascript
// 初始化 WebSocket
const socket = io();

// 接收新信号
socket.on('new_signal', function(data) {
    // 1. 弹窗通知
    showSignalToast(data);
    
    // 2. 语音播报
    if (voiceEnabled) {
        speakSignal(data);
    }
    
    // 3. 刷新数据
    loadCombineSignal();
});

// 语音播报
function speakSignal(signal) {
    const utterance = new SpeechSynthesisUtterance(
        `新信号：${signal.name}，价格${signal.price}`
    );
    utterance.lang = 'zh-CN';
    speechSynthesis.speak(utterance);
}
```

---

## 4. 接口设计

### 4.1 Socket 事件

| 事件名 | 方向 | 说明 |
|--------|------|------|
| `connect` | C→S | 客户端连接 |
| `disconnect` | C→S | 客户端断开 |
| `connection_status` | S→C | 连接状态通知 |
| `new_signal` | S→C | 新信号推送 |

### 4.2 信号数据格式

```json
{
    "time": "10:56:48",
    "code": "123456",
    "name": "某某转债",
    "code_gp": "000001",
    "name_gp": "平安银行",
    "price_now_zq": 121.64,
    "buy_price": 121.70,
    "sell_price": 122.10,
    "zf_30": 5.2,
    "zf_30_zq": 3.1
}
```

---

## 5. 使用方式

### 5.1 启动 WebSocket 版 Dashboard

```bash
# 安装依赖
pip install flask-socketio python-socketio simple-websocket

# 启动
python -m gs2026.dashboard.app_ws

# 访问
http://localhost:5000/monitor
```

### 5.2 监控程序集成

```python
from gs2026.utils.websocket_notifier import notify_new_signal

# 检测到新信号时
def on_new_signal_detected(signal_data):
    # 保存到数据库...
    
    # 推送 WebSocket 通知
    notify_new_signal(signal_data)
```

### 5.3 前端页面

使用 `monitor_ws.html` 替代 `monitor.html`:
- 自动连接 WebSocket
- 支持语音播报开关
- 实时弹窗通知

---

## 6. 配置

### 6.1 依赖
```
flask-socketio>=5.3.0
python-socketio>=5.9.0
simple-websocket>=1.0.0
```

### 6.2 启动参数
```python
socketio.run(app, host='0.0.0.0', port=5000, 
             debug=False, allow_unsafe_werkzeug=True)
```

---

## 7. 注意事项

### 7.1 浏览器兼容性
- 语音播报需要浏览器支持 `SpeechSynthesis`
- Chrome/Edge/Firefox 均支持

### 7.2 性能考虑
- WebSocket 连接使用异步处理
- 语音播报可开关
- 弹窗自动消失（5秒）

### 7.3 安全性
- `allow_unsafe_werkzeug=True` 仅用于内网
- 生产环境建议使用生产级 WSGI 服务器

---

## 8. 测试方案

### 8.1 功能测试
1. 启动 `app_ws.py`
2. 打开监控页面
3. 触发股债联动信号
4. 验证：
   - 弹窗显示
   - 语音播报
   - 数据刷新

### 8.2 兼容性测试
1. 测试原有 `app.py` 不受影响
2. 测试无 WebSocket 依赖时正常运行

---

## 9. 未来扩展

### 9.1 计划功能
- [ ] 支持多房间/频道
- [ ] 用户订阅特定信号类型
- [ ] 信号历史记录
- [ ] 推送统计

### 9.2 优化方向
- [ ] 使用生产级消息队列（Redis/RabbitMQ）
- [ ] 支持分布式部署
- [ ] 添加重连机制
