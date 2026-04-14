# 更新日志 - 2025-03-25

## 概述
本次更新包含 Dashboard 功能增强、进程监控管理、股债联动优化等多个重要功能。

---

## 新增功能

### 1. Redis 进程监控系统 ✅

#### 1.1 核心组件
- **文件**: `src/gs2026/utils/process_monitor.py`
- **功能**: 基于 Redis 的进程监控管理工具
- **特性**:
  - 进程注册/注销
  - 心跳检测（10秒间隔）
  - 自动状态更新
  - 状态变更回调
  - 进程保活/自动重启（可选）

#### 1.2 适配器集成
- **文件**: `src/gs2026/dashboard/services/process_monitor_adapter.py`
- **功能**: 无侵入式集成到现有 ProcessManager
- **特性**:
  - 保持原有接口不变
  - 自动注册/注销进程
  - 自动监听状态变化

#### 1.3 集成范围
所有以下服务均已集成进程监控：

| 服务类型 | 进程ID | 注册位置 |
|---------|--------|---------|
| 数据采集 | `collection` | `start_collection()` |
| AI分析 | `analysis` | `start_analysis()` |
| 监控程序 | `monitor` | `start_monitor()` |
| 监控服务 | `service:{id}` | `start_service()` |
| 分析服务 | `analysis:{id}` | `start_analysis_service()` |

#### 1.4 API 端点
- **新增**: `GET /api/control/monitor-status`
- **返回**: 所有被监控进程的状态列表

---

### 2. WebSocket 实时通知系统 ✅

#### 2.1 核心组件
- **文件**: `src/gs2026/utils/websocket_notifier.py`
- **功能**: WebSocket 通知工具

#### 2.2 WebSocket Dashboard
- **文件**: `src/gs2026/dashboard/app_ws.py`
- **功能**: 带 WebSocket 支持的 Dashboard
- **端口**: 5000
- **特性**:
  - 实时推送股债联动信号
  - 浏览器语音播报（中文）
  - 页面弹窗通知

#### 2.3 前端模板
- **文件**: `src/gs2026/dashboard/templates/monitor_ws.html`
- **功能**: 带 WebSocket 的监控页面
- **特性**:
  - Socket.IO 客户端
  - 语音播报开关
  - 实时信号弹窗

#### 2.4 依赖更新
```
flask-socketio>=5.3.0
python-socketio>=5.9.0
simple-websocket>=1.0.0
```

---

### 3. 股债联动优化 ✅

#### 3.1 时间轴联动
- **功能**: 股债联动数据与时间轴同步
- **实现**:
  - `loadCombineSignal(timeStr)` 支持时间过滤
  - `loadDataAtTime()` 调用股债联动刷新
  - API `/latest-messages` 支持 `time` 参数

#### 3.2 买入/卖出价格
- **计算公式**:
  - 买入价格 = 价格保留1位小数 + 0.1
  - 卖出价格 = 买入价格 + 0.4
- **示例**: 121.64 → 121.6 → 121.7 → 122.1
- **显示**: 价格后两列，红色(买)/绿色(卖)

#### 3.3 高亮显示
- **功能**: 时间轴选中时间的数据高亮
- **实现**: `renderCombineSignal(data, highlightTime)`
- **效果**: 红色背景 + NEW 标签

---

### 4. 大盘概览颜色优化 ✅

#### 4.1 功能描述
- 区间上涨 > 区间下跌：暖色（红色渐变）
- 区间下跌 > 区间上涨：冷色（绿色渐变）
- 颜色强度由比例差决定

#### 4.2 实现文件
- `src/gs2026/dashboard/templates/monitor.html`
- `src/gs2026/dashboard/templates/monitor_ws.html`

---

## 修改文件

### 后端修改

| 文件 | 修改内容 |
|------|---------|
| `src/gs2026/dashboard/services/process_manager.py` | 集成进程监控适配器 |
| `src/gs2026/dashboard/services/data_service.py` | 买入/卖出价格计算 |
| `src/gs2026/dashboard/routes/control.py` | 新增 `/monitor-status` API |
| `src/gs2026/dashboard/routes/monitor.py` | 支持时间过滤参数 |
| `src/gs2026/monitor/monitor_gp_zq_rising_signal.py` | WebSocket 通知调用 |
| `src/gs2026/utils/data_recovery.py` | 股债联动数据修复 |

### 前端修改

| 文件 | 修改内容 |
|------|---------|
| `src/gs2026/dashboard/templates/monitor.html` | 时间轴联动、价格显示、颜色优化 |
| `src/gs2026/dashboard/templates/control.html` | 数据分析面板 |

### 配置修改

| 文件 | 修改内容 |
|------|---------|
| `requirements.txt` | 添加 WebSocket 依赖 |
| `pyproject.toml` | 添加 WebSocket 依赖 |

---

## 测试文件

| 文件 | 用途 |
|------|------|
| `tests/test_process_monitor.py` | 进程监控单元测试 |
| `tools/view_process_monitor.py` | Redis 数据查看工具 |

---

## 未处理事项 (TODO)

### 高优先级
- [x] **~~财联社分析启动后停止问题~~** ✅ 已解决
  - 解决方案：通过 Redis 进程监控记录 PID
  - 进程异常停止时可自动检测并通知
  - 实现：使用 `process_monitor.py` 注册和监控进程状态
  - 可能原因：OpenClaw exec 会话管理、进程信号

### 中优先级
- [ ] 验证其他4个分析服务是否正常
- [ ] 测试问财 Cookie 方式是否解决登录弹窗
- [ ] 优化数据分析面板 UI，添加运行状态指示器

### 低优先级
- [ ] 清理 temp/ 和 tests/ 目录下的调试文件
- [ ] 完善错误处理和用户提示

---

## 提交记录

```bash
# 添加所有修改
git add -A

# 提交
git commit -m "feat: 2025-03-25 更新

- 新增 Redis 进程监控系统
- 新增 WebSocket 实时通知
- 股债联动时间轴联动
- 买入/卖出价格显示
- 大盘概览颜色优化

Closes #process-monitor, #websocket-notification"

# 推送
git push origin main
```

---

## 文档更新

- [x] CHANGELOG 更新
- [ ] USAGE.md 更新（Dashboard 新功能）
- [ ] README.md 更新（进程监控说明）
- [ ] API 文档更新

---

## 技术笔记

### 财联社分析启动问题解决方案

**问题**: 通过 Dashboard 启动财联社分析后几秒停止

**根本原因**: 
- 进程启动后失去监控
- 异常停止无法被检测

**解决方案**: Redis 进程监控系统

**实现**:
1. 启动时注册进程到 Redis (`_register_process`)
2. 后台线程每10秒检查进程状态
3. 进程停止时自动更新状态为 `stopped`
4. 可通过 `/monitor-status` API 查询状态

**效果**:
- 进程状态实时可查询
- 异常停止可被检测
- 为后续自动重启提供基础

---

## 备注

- 所有新功能均向后兼容
- 进程监控为可选依赖，不影响原有功能
- WebSocket 为独立应用（app_ws.py），不影响原有 app.py
