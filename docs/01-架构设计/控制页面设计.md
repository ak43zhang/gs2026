# 数据采集/分析页面设计文档

## 1. 页面概述

### 1.1 功能定位
- **数据采集 Tab**: 启动/停止五个监控服务（股票、债券、行业、大盘、股债）
- **数据分析 Tab**: 启动/停止五个AI分析服务（事件驱动、财联社、综合新闻、涨停板、公告）

### 1.2 核心特性
- 支持同一服务多开（最多5个实例）
- 实时显示运行中的进程及PID
- 可单独停止指定实例
- 自动刷新（10秒间隔）

---

## 2. 页面结构

```
┌─────────────────────────────────────────────────────────┐
│  📊 GS2026 数据采集 & 分析          [首页] [监控] [采集]  │
├─────────────────────────────────────────────────────────┤
│  [👁️ 数据采集] [🤖 数据分析]  ← Tab 切换                 │
├─────────────────────────────────────────────────────────┤
│  [▶ 启动全部] [⏹ 停止全部]                              │
├─────────────────────────────────────────────────────────┤
│  服务卡片网格                                            │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐          │
│  │股票监控│ │债券监控│ │行业监控│ │  ...   │          │
│  │[启动]  │ │[启动]  │ │[启动]  │ │[启动]  │          │
│  └────────┘ └────────┘ └────────┘ └────────┘          │
├─────────────────────────────────────────────────────────┤
│  ⚙️ 当前运行进程服务                                     │
│  ┌─────────────────────────────────────────────────────┐│
│  │ 股票监控_20260325_a1b2  监控服务  运行中 PID:12345 [停止]│
│  │ 财联社_20260325_b3c4    分析服务  运行中 PID:12346 [停止]│
│  │ 股票监控_20260324_d5e6  监控服务  已停止 PID:12347      │
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

---

## 3. HTML 结构

### 3.1 整体布局
```html
<body>
    <!-- 顶栏 -->
    <div class="topbar">...</div>
    
    <!-- 主容器 -->
    <div class="container">
        <!-- Tab 导航 -->
        <div class="tab-nav">
            <button onclick="switchTab('monitor', this)">数据采集</button>
            <button onclick="switchTab('analysis', this)">数据分析</button>
        </div>
        
        <!-- Tab1: 数据采集 -->
        <div class="tab-content active" id="tab-monitor">
            <!-- 全局操作 -->
            <div class="global-actions">...</div>
            
            <!-- 服务卡片网格 -->
            <div class="section">
                <div class="service-grid">...</div>
            </div>
            
            <!-- 当前进程 -->
            <div class="section">
                <div id="monitor-processes-list">...</div>
            </div>
        </div>
        
        <!-- Tab2: 数据分析 -->
        <div class="tab-content" id="tab-analysis">
            <!-- 类似结构 -->
        </div>
    </div>
</body>
```

### 3.2 关键元素

| 元素 | ID/Class | 说明 |
|------|----------|------|
| Tab 按钮 | `.tab-btn` | 切换显示 |
| Tab 内容 | `.tab-content` | 数据采集/分析 |
| 服务卡片 | `.service-card` | 单个服务 |
| 进程列表 | `.process-list` | 显示运行中的进程 |

---

## 4. CSS 样式

### 4.1 Tab 切换
```css
.tab-content { display: none; }
.tab-content.active { display: block; }
.tab-btn.active { background: #667eea; color: white; }
```

### 4.2 服务卡片
```css
.service-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
}
.service-card {
    background: #f8f9fb;
    padding: 16px;
    border-radius: 8px;
}
```

### 4.3 进程列表
```css
.process-item {
    display: flex;
    justify-content: space-between;
    padding: 10px 12px;
    border-left: 3px solid #43a047; /* 运行中绿色 */
}
.process-item.stopped {
    border-left-color: #e53935; /* 已停止红色 */
}
```

---

## 5. JavaScript 逻辑

### 5.1 Tab 切换
```javascript
function switchTab(tab, btn) {
    // 移除所有 active
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    // 添加 active 到当前
    document.getElementById('tab-' + tab).classList.add('active');
    if (btn) btn.classList.add('active');
}
```

### 5.2 加载进程列表
```javascript
async function loadRunningProcesses() {
    const r = await fetch('/api/control/monitor-status');
    const data = await r.json();
    renderProcessList(data.data);
}

// 每10秒刷新
setInterval(loadRunningProcesses, 10000);
```

### 5.3 停止指定实例
```javascript
async function stopProcessInstance(processId) {
    const url = `/api/control/stop-service-instance/${processId}`;
    await fetch(url, { method: 'POST' });
    loadRunningProcesses(); // 刷新列表
}
```

---

## 6. API 接口

### 6.1 获取进程状态
```http
GET /api/control/monitor-status

Response:
{
    "success": true,
    "data": [
        {
            "process_id": "stock_20260325_a1b2",
            "service_id": "stock",
            "instance_id": "20260325_a1b2",
            "pid": 12345,
            "status": "running",
            "process_type": "monitor_service",
            "params": {"filename": "monitor_stock.py"}
        }
    ]
}
```

### 6.2 停止指定实例
```http
POST /api/control/stop-service-instance/{process_id}
POST /api/control/stop-analysis-instance/{process_id}
```

---

## 7. 进程命名规范

### 7.1 格式
```
{service_id}_{date}_{random}

示例：
- stock_20260325_a1b2
- news_cls_20260325_b3c4
- event_driven_20260325_c5d6
```

### 7.2 组成部分
| 部分 | 说明 | 示例 |
|------|------|------|
| service_id | 服务标识 | stock, news_cls |
| date | 日期 | 20260325 |
| random | 随机4位 | a1b2, b3c4 |

---

## 8. 多开限制

### 8.1 默认配置
- 同一服务最大实例数：5个
- 超过限制时提示："已达到最大实例数限制 (5)"

### 8.2 检查逻辑
```python
def _check_max_instances(self, service_id: str, max_instances: int = 5) -> bool:
    running_count = self._monitor.get_running_count(service_id)
    return running_count < max_instances
```

---

## 9. 历史记录

### 9.1 保留策略
- 运行中的进程：实时显示
- 已停止的进程：保留7天
- 排序：运行中的在前，停止的按停止时间倒序

### 9.2 清理任务
```python
def cleanup_stopped(self, max_age_days: int = 7) -> int:
    # 清理7天前停止的进程
    pass
```

---

## 10. 文件清单

| 文件 | 说明 |
|------|------|
| `templates/control.html` | 页面模板 |
| `routes/control.py` | API路由 |
| `services/process_manager.py` | 进程管理 |
| `utils/process_monitor.py` | 进程监控 |

---

## 11. 注意事项

### 11.1 HTML 结构
- 确保所有 `<div>` 正确闭合
- Tab 内容使用 `display: none/block` 切换
- 避免重复代码块

### 11.2 JavaScript
- 使用 `event` 参数传递按钮元素
- 定期刷新进程状态
- 停止前确认提示

### 11.3 后端
- 进程ID全局唯一
- 记录启动参数
- 自动检测进程停止
