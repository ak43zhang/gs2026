# Dashboard2 数据分析模块设计方案文档

## 文档信息
- **创建日期**: 2026-03-27
- **最后更新**: 2026-03-27 18:58
- **版本**: v1.0

---

## 1. 项目概述

### 1.1 目标
开发数据分析模块，与数据采集模块同构，支持5个DeepSeek AI分析任务。

### 1.2 架构原则
- 完全复用数据采集的组件体系
- 不影响原有代码逻辑
- 向后兼容，新增功能独立

---

## 2. 系统架构

### 2.1 文件结构
```
dashboard2/
├── routes/
│   ├── analysis.py              # 分析路由API (5个端点)
│   └── analysis_modules.py      # 分析模块配置
├── static/
│   └── js/
│       ├── modules/
│       │   └── analysis-manager.js   # 分析管理器
│       └── pages/
│           └── analysis-page.js      # 分析页面
└── templates/
    └── analysis.html            # 分析页面模板
```

### 2.2 与数据采集架构对比

| 组件 | 数据采集 | 数据分析 |
|------|----------|----------|
| 配置 | `collection.py` | `analysis_modules.py` |
| 路由 | `collection.py` | `analysis.py` |
| Manager | `CollectionManager` | `AnalysisManager` |
| Page | `CollectionPage` | `AnalysisPage` |
| 日期工具栏 | 有 | **无** |

---

## 3. 任务配置设计

### 3.1 5个分析任务

```python
ANALYSIS_MODULES = {
    'deepseek': {
        'name': 'DeepSeek AI分析',
        'icon': '🤖',
        'type': 'analysis',
        'tasks': {
            'event_driven': {
                'name': '领域事件分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_event_driven.py',
                'function': 'analysis_event_driven',
                'params': [
                    {
                        'name': 'date_list',
                        'type': 'date_list',  # 自定义类型
                        'label': '分析日期列表',
                        'required': True,
                        'description': '选择需要分析的日期，可添加多个'
                    }
                ]
            },
            'news_cls': {
                'name': '财联社数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_cls.py',
                'function': 'analysis_news_cls',
                'params': []
            },
            'news_combine': {
                'name': '综合数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_combine.py',
                'function': 'analysis_news_combine',
                'params': []
            },
            'news_ztb': {
                'name': '涨停板数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_ztb.py',
                'function': 'analysis_news_ztb',
                'params': []
            },
            'notice': {
                'name': '公告分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_notice.py',
                'function': 'analysis_notice',
                'params': []
            }
        }
    }
}
```

---

## 4. 日期列表参数设计

### 4.1 需求背景
领域事件分析需要接收日期列表参数，如 `['2026-03-20', '2026-03-21']`。

### 4.2 UI设计方案

```
┌─────────────────────────────────────────┐
│  📅 领域事件分析                          │
├─────────────────────────────────────────┤
│  分析日期列表:                            │
│  ┌─────────────┐ [➕ 添加]              │
│  │ 2026-03-27 │                          │
│  └─────────────┘                          │
│  ┌─────────────────────────────────┐    │
│  │ 📅 2026-03-27              [❌] │    │
│  │ 📅 2026-03-26              [❌] │    │
│  │ 📅 2026-03-25              [❌] │    │
│  └─────────────────────────────────┘    │
│  [▶️ 启动分析]                          │
└─────────────────────────────────────────┘
```

### 4.3 实现方案

#### 4.3.1 前端实现

**ServiceCard 组件扩展**:

```javascript
// 1. 渲染日期列表参数
renderDateListParam(param, inputId) {
    return `
        <div class="param-row date-list-param" data-param-name="${param.name}">
            <label class="param-label">${param.label}</label>
            <div class="date-list-input-group">
                <input type="date" id="${inputId}-picker" class="date-picker">
                <button type="button" class="btn btn-add-date" data-param="${param.name}">➕ 添加</button>
            </div>
            <div class="date-list-container" id="${inputId}-list">
                <div class="date-list-empty">暂无日期，请添加</div>
            </div>
            <input type="hidden" id="${inputId}" class="date-list-hidden" value="[]">
        </div>
    `;
}

// 2. 添加日期到列表
addDateToList(paramName, dateValue) {
    // 设置编辑状态，防止状态更新导致重新渲染
    this.isEditing = true;
    
    // 获取当前列表
    let dateList = JSON.parse(hiddenInput.value || '[]');
    
    // 检查重复
    if (dateList.includes(dateValue)) {
        alert('该日期已存在');
        return;
    }
    
    // 添加并排序
    dateList.push(dateValue);
    dateList.sort();
    hiddenInput.value = JSON.stringify(dateList);
    
    // 更新显示
    this.renderDateList(listContainer, paramName, dateList);
    // 注意：不自动重置 isEditing，保持编辑状态
}

// 3. 从列表删除日期
removeDateFromList(paramName, dateValue) {
    this.isEditing = true;
    
    let dateList = JSON.parse(hiddenInput.value || '[]');
    dateList = dateList.filter(d => d !== dateValue);
    hiddenInput.value = JSON.stringify(dateList);
    
    this.renderDateList(listContainer, paramName, dateList);
}

// 4. 获取参数时解析JSON
getParams() {
    if (input.classList.contains('date-list-hidden')) {
        try {
            params[name] = JSON.parse(input.value || '[]');
        } catch (e) {
            params[name] = [];
        }
    }
}
```

#### 4.3.2 编辑锁定机制

**问题**: 状态轮询导致页面重新渲染，重置日期列表。

**解决方案**:

```javascript
// updateStatus 方法
updateStatus(status) {
    this.status = status;
    
    // 如果正在编辑，只更新状态指示器
    if (this.isEditing) {
        this.updateStatusOnly(status);
        return;
    }
    
    // 正常重新渲染
    this.render({ taskId: this.taskId, config: this.config, status });
}

// 仅更新状态指示器（不重新渲染参数区域）
updateStatusOnly(status) {
    // 更新状态类
    card.classList.remove('running', 'executing', 'completed', 'stopped');
    card.classList.add(statusClass);
    
    // 更新状态文字
    statusTextEl.textContent = statusText;
    
    // 更新PID显示
    pidEl.textContent = status.pid ? `PID:${status.pid}` : '';
    
    // 更新按钮状态
    startBtn.disabled = status.status === 'running';
    stopBtn.disabled = status.status !== 'running';
}
```

**状态流转**:
```
用户添加日期 → isEditing = true → 日期列表更新
       ↓
状态轮询触发 → 检测到 isEditing = true
       ↓
调用 updateStatusOnly() → 只更新状态指示器
       ↓
参数区域保持不变 → 日期列表保留

用户点击启动 → isEditing = false → 正常渲染
```

#### 4.3.3 CSS样式

```css
/* 日期列表参数样式 */
.date-list-param {
    flex-direction: column;
    align-items: stretch;
}

.date-list-input-group {
    display: flex;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-xs);
}

.date-list-container {
    max-height: 120px;
    overflow-y: auto;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: var(--spacing-xs);
}

.date-list-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    margin-bottom: 4px;
    background: var(--bg-secondary);
    border-radius: 4px;
}
```

#### 4.3.4 后端实现

```python
@analysis_bp.route('/<module_id>/start/<task_id>', methods=['POST'])
def start_task(module_id, task_id):
    # 获取请求参数
    request_data = request.get_json() or {}
    
    # 对于 date_list 参数，需要特殊处理
    params = {}
    if 'date_list' in request_data:
        params['date_list'] = request_data['date_list']
    
    result = process_manager.start_monitor_service(
        service_id=f'analysis_{task_id}',
        script_name=task['file'],
        params=params
    )
```

---

## 5. 卡片容器设计

### 5.1 问题
多个 `ServiceCard` 实例共享同一个容器 `'service-grid'`，后面的卡片会清空前面卡片的内容。

### 5.2 解决方案
为每个卡片创建独立的容器元素：

```javascript
// 创建新卡片
tasksData.forEach((task, index) => {
    // 为每个卡片创建独立的容器
    const cardContainer = document.createElement('div');
    cardContainer.id = `task-card-${task.id}`;
    this.components.serviceGrid.container.appendChild(cardContainer);
    
    const card = new ServiceCard(cardContainer.id, {
        taskId: task.id,
        moduleId: moduleId,
        config: { name: task.name, params: task.params || [] },
        status: { running: false }
    });
    
    card.render();
    this.components.serviceGrid.cards.set(task.id, card);
});
```

---

## 6. 组件继承关系

### 6.1 类图

```
BaseComponent
    ├── ServiceCard
    ├── TabNav
    └── ProcessList

BaseManager
    └── AnalysisManager

独立类
    └── AnalysisPage
```

### 6.2 ServiceCard 配置格式

```javascript
{
    taskId: 'event_driven',      // 任务ID
    moduleId: 'deepseek',        // 模块ID
    config: {
        name: '领域事件分析',     // 任务名称
        params: [                 // 参数配置
            { name: 'date_list', type: 'date_list', label: '分析日期列表' }
        ]
    },
    status: {                     // 初始状态
        running: false,
        status: 'stopped'
    },
    on: {                         // 事件回调
        start: ({ taskId, params }) => {...},
        stop: ({ taskId }) => {...}
    }
}
```

---

## 7. API 端点设计

### 7.1 分析模块 API

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/analysis/modules` | 获取所有模块 |
| GET | `/api/analysis/<module_id>/tasks` | 获取模块任务列表 |
| POST | `/api/analysis/<module_id>/start/<task_id>` | 启动任务 |
| POST | `/api/analysis/stop/<process_id>` | 停止任务 |
| GET | `/api/analysis/status` | 获取所有任务状态 |

### 7.2 请求/响应示例

**启动任务（带日期列表）**:
```http
POST /api/analysis/deepseek/start/event_driven
Content-Type: application/json

{
    "date_list": ["2026-03-27", "2026-03-26", "2026-03-25"]
}
```

```json
{
    "success": true,
    "process_id": "analysis_event_driven_abc123",
    "pid": 12345,
    "message": "任务已启动"
}
```

---

## 8. 关键设计决策

### 8.1 为什么不使用 `config/` 目录？
- 创建 `config/__init__.py` 会干扰 `config.py` 的导入
- 解决方案：将配置移到 `routes/analysis_modules.py`

### 8.2 为什么 `ServiceCard` 不继承 `BaseComponent` 的 `render`？
- `BaseComponent.render()` 会清空容器 `innerHTML`
- 多个卡片共享容器会导致相互覆盖
- 解决方案：为每个卡片创建独立容器

### 8.3 为什么 `isEditing` 不自动解锁？
- 自动解锁（setTimeout）可能在状态轮询前执行
- 解决方案：保持 `isEditing = true` 直到用户点击启动/停止

### 8.4 为什么轮询间隔改为10秒？
- 减少刷新频率，降低对编辑操作的干扰
- 平衡实时性和用户体验

---

## 9. 向后兼容性

### 9.1 参数类型兼容性

| 类型 | 原有支持 | 新增支持 |
|------|----------|----------|
| date | ✅ | - |
| datetime | ✅ | - |
| number | ✅ | - |
| boolean | ✅ | - |
| text | ✅ | - |
| **date_list** | - | ✅ 新增 |

### 9.2 不影响原有功能的修改
- 新增文件完全独立
- 修改文件通过 `if (p.type === 'date_list')` 判断，不影响其他类型
- CSS 新增类名，不覆盖原有样式

---

## 10. 已知Bug记录

### Bug #1: 数据分析启动报错

**状态**: 🔴 待修复  
**发现时间**: 2026-03-27 19:09  
**优先级**: 高

#### 问题描述
数据分析模块点击启动按钮时报错，无法正常启动分析任务。

#### 错误信息
```
[待补充完整错误日志]
```

#### 可能原因
1. `process_manager.start_monitor_service` 参数传递问题
2. 分析脚本路径解析错误
3. 日期列表参数格式不匹配
4. 进程注册失败

#### 相关代码
- `analysis.py` - `start_task` 函数
- `process_manager.py` - `start_monitor_service` 函数
- `analysis_modules.py` - 任务配置

#### 修复计划
- [ ] 检查 `start_monitor_service` 调用参数
- [ ] 验证分析脚本文件路径
- [ ] 确认日期列表参数传递格式
- [ ] 添加详细错误日志

---

## 11. 待优化项

- [ ] 日期列表支持拖拽排序
- [ ] 支持批量导入日期（如从文件）
- [ ] 日期列表缓存，页面刷新后保留
- [ ] 支持日期范围选择（开始日期-结束日期）

---

## 附录：相关文件路径

```
F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\
├── routes/
│   ├── analysis.py
│   └── analysis_modules.py
├── static/
│   ├── css/
│   │   └── components.css
│   └── js/
│       ├── components/
│       │   └── service-card.js
│       ├── modules/
│       │   └── analysis-manager.js
│       └── pages/
│           └── analysis-page.js
└── templates/
    └── analysis.html

F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\
├── deepseek_analysis_event_driven.py
├── deepseek_analysis_news_cls.py
├── deepseek_analysis_news_combine.py
├── deepseek_analysis_news_ztb.py
└── deepseek_analysis_notice.py
```
