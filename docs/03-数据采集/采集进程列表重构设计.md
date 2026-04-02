# 数据采集当前运行进程显示重构方案

## 背景

当前数据采集页面的"当前运行进程"部分存在以下问题：
1. 进程显示逻辑与分析页面不一致
2. 进程ID管理混乱，不支持多开
3. 状态同步不够实时
4. 停止功能偶尔失效

## 目标

将数据采集的进程显示重构为与数据分析页面相同的模式：
- 使用 `process_id` 作为唯一键
- 支持同一任务的多个实例（多开）
- 使用 `ProcessList` 组件统一显示
- 统一的后端状态管理

---

## 一、当前实现差异分析

### 1.1 AnalysisManager（数据分析）✅ 已优化

```javascript
class AnalysisManager {
    constructor() {
        this.runningTasks = new Map();  // key: process_id
    }
    
    async startTask(moduleId, taskId, params) {
        // 返回: { success, process_id, pid }
        const result = await api.post(`/analysis/${moduleId}/start/${taskId}`, params);
        // process_id 格式: "analysis_event_driven_20260331223045_a1b2c3d4"
        return result;
    }
    
    async refreshStatus() {
        // 清空重新填充
        this.runningTasks.clear();
        result.data.processes.forEach(proc => {
            if (proc.status === 'running') {
                // 解析 moduleId 和 taskId
                const serviceId = proc.service_id;
                const moduleId = 'deepseek';
                const taskId = serviceId.replace('analysis_', '');
                
                this.runningTasks.set(proc.process_id, {
                    processId: proc.process_id,
                    moduleId: moduleId,
                    taskId: taskId,
                    // ...
                });
            }
        });
    }
    
    async stopTask(processId) {
        // 使用 process_id 停止
        await api.post(`/analysis/stop/${processId}`);
        this.runningTasks.delete(processId);
    }
}
```

### 1.2 CollectionManager（数据采集）⚠️ 待优化

```javascript
class CollectionManager {
    constructor() {
        this.runningTasks = new Map();  // key: process_id
    }
    
    async startTask(moduleId, taskId, params) {
        // 返回: { success, process_id, pid }
        const result = await api.post(`/collection/start/${taskId}`, params);
        // process_id 格式: "collection_任务名_时间戳"
        return result;
    }
    
    async refreshStatus() {
        // 存在问题: 没有清空，而是增量更新
        const result = await api.get('/collection/status');
        result.data.forEach(proc => {
            if (proc.status === 'running') {
                this.runningTasks.set(proc.process_id, proc);
            }
        });
    }
    
    async stopTask(processId) {
        // 使用 process_id 停止
        await api.post(`/collection/stop/${processId}`);
    }
}
```

### 1.3 关键差异

| 方面 | AnalysisManager | CollectionManager | 问题 |
|------|----------------|-------------------|------|
| 状态刷新 | `clear()` 后重新填充 | 增量更新 | 数据可能不一致 |
| 数据解析 | 解析 `service_id` 提取 module/task | 直接使用后端数据 | 前端缺少模块信息 |
| 多开支持 | ✅ 支持 | ⚠️ 部分支持 | 需要确认 |
| 停止功能 | ✅ 正常 | ⚠️ 偶尔失败 | 需要修复 |

---

## 二、重构方案

### 2.1 前端修改

#### 2.1.1 CollectionManager 修改

**文件**: `static/js/modules/collection-manager.js`

```javascript
// 修改 refreshStatus 方法
async refreshStatus() {
    try {
        const result = await GS2026.api.get('/collection/status');
        
        // 改为清空重新填充（与 AnalysisManager 一致）
        this.runningTasks.clear();
        
        if (result.data) {
            result.data.forEach(proc => {
                if (proc.status === 'running') {
                    // 解析 moduleId 和 taskId（类似 AnalysisManager）
                    const processId = proc.process_id;
                    const serviceId = proc.service_id || processId;
                    
                    // 从 service_id 解析 module 和 task
                    // collection_模块_任务_时间戳 或 collection_任务_时间戳
                    let moduleId = 'unknown';
                    let taskId = serviceId;
                    
                    // 尝试从配置中匹配
                    for (const [modId, module] of Object.entries(this.modules)) {
                        for (const [tid, task] of Object.entries(module.tasks || {})) {
                            if (serviceId.includes(tid) || processId.includes(tid)) {
                                moduleId = modId;
                                taskId = tid;
                                break;
                            }
                        }
                        if (moduleId !== 'unknown') break;
                    }
                    
                    this.runningTasks.set(processId, {
                        processId: processId,
                        serviceId: serviceId,
                        moduleId: moduleId,
                        taskId: taskId,
                        pid: proc.pid,
                        status: proc.status,
                        startTime: new Date(proc.start_time).getTime(),
                        params: proc.params || {}
                    });
                }
            });
        }

        this.emit('statusRefreshed', this.getRunningTasks());
        return result;
    } catch (e) {
        this.log('error', 'Failed to refresh status', { error: e.message });
        throw e;
    }
}
```

#### 2.1.2 collection-page.js 修改

**文件**: `static/js/pages/collection-page.js`

```javascript
// 修改进程列表渲染
renderProcessList() {
    const processList = this.$('#process-list');
    if (!processList) return;
    
    // 使用 ProcessList 组件（与 analysis.html 一致）
    if (!this.processListComponent) {
        this.processListComponent = new ProcessList('process-list', {
            showStopButton: true,
            emptyText: '暂无运行中的采集任务'
        });
        
        // 绑定停止事件
        this.processListComponent.on('stop', ({ processId }) => {
            this.handleStopProcess(processId);
        });
        
        this.processListComponent.on('stopAll', () => {
            this.handleStopAll();
        });
    }
    
    // 转换数据格式
    const processes = this.collectionManager.getRunningTasks().map(task => ({
        process_id: task.processId,
        service_id: task.serviceId,
        module: task.moduleId,
        taskId: task.taskId,
        pid: task.pid,
        status: task.status,
        start_time: task.startTime
    }));
    
    this.processListComponent.setProcesses(processes);
}
```

#### 2.1.3 collection.html 修改

**文件**: `templates/collection.html`

```html
<!-- 修改进程列表部分 -->
<div class="process-section">
    <h3>当前运行进程</h3>
    <!-- 使用统一的 ProcessList 组件 -->
    <div id="process-list"></div>
</div>
```

### 2.2 后端修改

#### 2.2.1 collection.py 修改

**文件**: `routes/collection.py`

```python
@collection_bp.route('/status', methods=['GET'])
def get_status():
    """获取采集任务状态 - 重构后"""
    if not PM_AVAILABLE or process_manager is None:
        return jsonify({
            'code': 200,
            'data': [],
            'message': 'ProcessManager not available'
        })
    
    try:
        # 获取所有进程状态
        all_processes = process_manager.get_all_processes()
        
        # 过滤采集类进程
        collection_processes = []
        for proc in all_processes:
            service_id = proc.get('service_id', '')
            # 只返回采集类进程
            if service_id.startswith('collection_'):
                collection_processes.append({
                    'process_id': proc.get('process_id'),
                    'service_id': service_id,
                    'pid': proc.get('pid'),
                    'status': proc.get('status'),
                    'start_time': proc.get('start_time'),
                    'params': proc.get('params', {})
                })
        
        return jsonify({
            'code': 200,
            'data': collection_processes
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': str(e)
        }), 500
```

#### 2.2.2 ProcessManager 优化

**文件**: `dashboard/services/process_manager.py`

```python
def start_collection_task(self, task_id, params=None, working_dir=None):
    """启动采集任务 - 生成规范化的 process_id"""
    import uuid
    from datetime import datetime
    
    # 生成唯一的 process_id
    # 格式: collection_{模块}_{任务}_{时间戳}_{随机后缀}
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = uuid.uuid4().hex[:8]
    
    # 尝试从 task_id 解析模块
    module_id = 'base'  # 默认模块
    task_name = task_id
    
    # 如果 task_id 包含模块信息，解析出来
    if '_' in task_id:
        parts = task_id.split('_')
        if parts[0] in ['monitor', 'base', 'news', 'risk']:
            module_id = parts[0]
            task_name = '_'.join(parts[1:])
    
    process_id = f"collection_{module_id}_{task_name}_{timestamp}_{random_suffix}"
    
    # ... 启动进程逻辑
    
    return {
        'success': True,
        'process_id': process_id,
        'pid': pid
    }
```

### 2.3 ProcessList 组件优化

**文件**: `static/js/components/process-list.js`

```javascript
// 增强 module 和 task 名称解析
getModuleName(moduleId) {
    const moduleNames = {
        'monitor': '开市采集',
        'base': '基础采集',
        'news': '消息采集',
        'risk': '风险采集',
        'deepseek': 'AI分析',
        'unknown': '未知模块'
    };
    return moduleNames[moduleId] || moduleId;
}

getTaskName(moduleId, taskId) {
    // 尝试从配置中获取任务名称
    if (window.GS2026 && window.GS2026.config) {
        const modules = window.GS2026.config.collectionModules || 
                       window.GS2026.config.analysisModules || {};
        const module = modules[moduleId];
        if (module && module.tasks && module.tasks[taskId]) {
            return module.tasks[taskId].name || taskId;
        }
    }
    
    // 默认返回 taskId
    return taskId;
}
```

---

## 三、实施步骤

### 步骤1: 修改后端 collection.py（低风险）
- [ ] 修改 `/status` 接口返回格式
- [ ] 确保 `process_id` 生成规范
- [ ] 测试接口返回数据

### 步骤2: 修改前端 CollectionManager（中风险）
- [ ] 重构 `refreshStatus()` 方法
- [ ] 添加 module/task 解析逻辑
- [ ] 测试状态刷新

### 步骤3: 修改 collection-page.js（中风险）
- [ ] 使用 ProcessList 组件
- [ ] 绑定停止事件
- [ ] 测试进程列表显示

### 步骤4: 修改 collection.html（低风险）
- [ ] 简化进程列表HTML结构
- [ ] 引入 ProcessList 组件
- [ ] 测试页面渲染

### 步骤5: 集成测试（高风险）
- [ ] 测试启动任务
- [ ] 测试停止任务
- [ ] 测试多开功能
- [ ] 测试状态同步

---

## 四、风险与回滚

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 停止功能失效 | 高 | 保留原有停止逻辑作为fallback |
| 状态显示错误 | 中 | 增加数据校验和日志 |
| 多开功能异常 | 中 | 逐步替换，保留旧代码注释 |

### 回滚方案
1. 保留原有代码注释
2. 使用 Git 分支开发
3. 关键修改添加 feature flag

---

## 五、预期效果

### 重构前
```
当前运行进程:
- PID:1234 股票监控 [停止]  
- PID:5678 债券监控 [停止]
(偶尔出现重复PID)
```

### 重构后
```
当前运行进程: 2 (运行中: 2)

开市采集
  股票监控              [运行中] PID:1234  00:05:32  [⏹️]
  债券监控              [运行中] PID:5678  00:03:15  [⏹️]
                    [全部停止]
```

---

## 六、相关文件

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `routes/collection.py` | 修改 | 状态接口返回格式 |
| `static/js/modules/collection-manager.js` | 重构 | 状态刷新逻辑 |
| `static/js/pages/collection-page.js` | 修改 | 使用ProcessList |
| `templates/collection.html` | 修改 | 简化HTML结构 |
| `static/js/components/process-list.js` | 增强 | module/task解析 |

---

*设计日期: 2026-04-01*
*状态: 待确认*
