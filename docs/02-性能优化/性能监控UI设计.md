# 性能监控界面完整设计方案

> 设计时间: 2026-03-31 08:35  
> 目标: 在报表中心后增加性能监控导航，集成三个监控工具

---

## 一、整体架构

### 1.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     导航栏 (原有)                            │
│  首页 | 数据采集 | 数据分析 | 数据监控 | 报表中心 | 性能监控  │  ← 新增
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    性能监控页面 (performance.html)           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ API性能监控 │  │ 数据库分析  │  │ 前端性能    │         │
│  │   卡片      │  │   卡片      │  │   卡片      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                    详细监控面板                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  实时请求列表 / 慢查询列表 / 资源加载列表            │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  性能趋势图表 (近1小时/6小时/24小时)                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **非侵入** | 不修改现有业务代码，独立模块 |
| **可插拔** | 通过settings.yaml启用/禁用 |
| **轻量级** | 复用现有诊断API，不新增后台服务 |
| **实时性** | 5秒自动刷新，支持手动刷新 |
| **可视化** | 图表展示趋势，表格展示详情 |

---

## 二、后端设计

### 2.1 复用现有API

已有API无需修改：
- `GET /diag/performance` - API性能统计
- `POST /diag/performance/reset` - 重置API统计
- `GET /diag/db` - 数据库分析统计

### 2.2 新增API（可选增强）

如需历史趋势，新增：

```python
# routes/performance.py
@performance_bp.route('/api/performance/history')
def get_performance_history():
    """获取性能历史数据（近N小时）"""
    hours = request.args.get('hours', 1, type=int)
    # 从日志文件或内存中聚合历史数据
    return jsonify({
        'timestamps': ['08:00', '08:05', '08:10', ...],
        'api_avg': [45, 52, 38, ...],
        'api_p95': [89, 95, 76, ...],
        'db_avg': [15, 18, 12, ...],
    })
```

**建议**: 第一阶段不复用现有API，不新增历史API，保持简单。

---

## 三、前端设计

### 3.1 页面结构

```html
<!-- templates/performance.html -->
<!DOCTYPE html>
<html>
<head>
    <title>性能监控 - GS2026</title>
    <!-- 复用现有样式 -->
    <link rel="stylesheet" href="/static/css/common.css">
    <!-- 图表库 -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <!-- 导航栏（与其他页面一致） -->
    {% include 'nav.html' %}
    
    <div class="container">
        <!-- 页面标题 -->
        <div class="page-header">
            <h1>⚡ 性能监控中心</h1>
            <div class="header-actions">
                <button onclick="refreshAll()">🔄 刷新</button>
                <button onclick="resetAll()">🗑️ 重置统计</button>
                <label>
                    <input type="checkbox" id="auto-refresh" checked> 自动刷新(5s)
                </label>
            </div>
        </div>
        
        <!-- 概览卡片 -->
        <div class="overview-cards">
            <!-- API性能卡片 -->
            <div class="perf-card" id="api-card">
                <div class="card-header">
                    <h3>📊 API性能</h3>
                    <span class="status-badge" id="api-status">运行中</span>
                </div>
                <div class="card-body">
                    <div class="metric-row">
                        <span class="metric-label">总请求</span>
                        <span class="metric-value" id="api-total">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">平均响应</span>
                        <span class="metric-value" id="api-avg">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">P95响应</span>
                        <span class="metric-value" id="api-p95">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">慢请求</span>
                        <span class="metric-value warning" id="api-slow">-</span>
                    </div>
                </div>
            </div>
            
            <!-- 数据库卡片 -->
            <div class="perf-card" id="db-card">
                <div class="card-header">
                    <h3>🗄️ 数据库</h3>
                    <span class="status-badge" id="db-status">运行中</span>
                </div>
                <div class="card-body">
                    <div class="metric-row">
                        <span class="metric-label">总查询</span>
                        <span class="metric-value" id="db-total">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">平均耗时</span>
                        <span class="metric-value" id="db-avg">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">最大耗时</span>
                        <span class="metric-value" id="db-max">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">慢查询</span>
                        <span class="metric-value warning" id="db-slow">-</span>
                    </div>
                </div>
            </div>
            
            <!-- 前端性能卡片 -->
            <div class="perf-card" id="frontend-card">
                <div class="card-header">
                    <h3>🌐 前端性能</h3>
                    <span class="status-badge" id="frontend-status">运行中</span>
                </div>
                <div class="card-body">
                    <div class="metric-row">
                        <span class="metric-label">总请求</span>
                        <span class="metric-value" id="fe-total">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">平均耗时</span>
                        <span class="metric-value" id="fe-avg">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">最大耗时</span>
                        <span class="metric-value" id="fe-max">-</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">XHR请求</span>
                        <span class="metric-value" id="fe-xhr">-</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 详细面板 -->
        <div class="detail-panels">
            <!-- Tab切换 -->
            <div class="tab-header">
                <button class="tab-btn active" data-tab="api">API请求详情</button>
                <button class="tab-btn" data-tab="db">数据库查询</button>
                <button class="tab-btn" data-tab="frontend">前端资源</button>
            </div>
            
            <!-- API请求列表 -->
            <div class="tab-content active" id="api-panel">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>方法</th>
                            <th>路径</th>
                            <th>状态</th>
                            <th>耗时</th>
                            <th>DB查询</th>
                            <th>Redis查询</th>
                        </tr>
                    </thead>
                    <tbody id="api-table-body">
                        <!-- 动态填充 -->
                    </tbody>
                </table>
            </div>
            
            <!-- 数据库查询列表 -->
            <div class="tab-content" id="db-panel">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>SQL语句</th>
                            <th>耗时</th>
                        </tr>
                    </thead>
                    <tbody id="db-table-body">
                        <!-- 动态填充 -->
                    </tbody>
                </table>
            </div>
            
            <!-- 前端资源列表 -->
            <div class="tab-content" id="frontend-panel">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>类型</th>
                            <th>URL</th>
                            <th>耗时</th>
                            <th>大小</th>
                        </tr>
                    </thead>
                    <tbody id="fe-table-body">
                        <!-- 动态填充 -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script src="/static/js/performance.js"></script>
</body>
</html>
```

### 3.2 样式设计

```css
/* static/css/performance.css */

/* 页面容器 */
.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

/* 页面标题 */
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
}

.page-header h1 {
    font-size: 24px;
    color: #333;
}

.header-actions {
    display: flex;
    gap: 12px;
    align-items: center;
}

.header-actions button {
    padding: 8px 16px;
    border: 1px solid #d9d9d9;
    background: white;
    border-radius: 4px;
    cursor: pointer;
}

.header-actions button:hover {
    border-color: #40a9ff;
    color: #40a9ff;
}

/* 概览卡片 */
.overview-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
    margin-bottom: 24px;
}

.perf-card {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    padding: 20px;
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #f0f0f0;
}

.card-header h3 {
    font-size: 16px;
    color: #333;
    margin: 0;
}

.status-badge {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    background: #f6ffed;
    color: #52c41a;
    border: 1px solid #b7eb8f;
}

.status-badge.disabled {
    background: #fff1f0;
    color: #ff4d4f;
    border-color: #ffa39e;
}

.metric-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #f5f5f5;
}

.metric-row:last-child {
    border-bottom: none;
}

.metric-label {
    color: #666;
    font-size: 14px;
}

.metric-value {
    font-size: 14px;
    font-weight: 600;
    color: #333;
}

.metric-value.warning {
    color: #ff4d4f;
}

/* Tab切换 */
.detail-panels {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.tab-header {
    display: flex;
    border-bottom: 1px solid #f0f0f0;
    padding: 0 20px;
}

.tab-btn {
    padding: 12px 20px;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 14px;
    color: #666;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
}

.tab-btn:hover {
    color: #40a9ff;
}

.tab-btn.active {
    color: #1890ff;
    border-bottom-color: #1890ff;
}

.tab-content {
    display: none;
    padding: 20px;
}

.tab-content.active {
    display: block;
}

/* 数据表格 */
.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table th,
.data-table td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid #f0f0f0;
}

.data-table th {
    font-weight: 600;
    color: #333;
    background: #fafafa;
}

.data-table tr:hover {
    background: #f5f5f5;
}

/* 耗时颜色 */
.duration-good { color: #52c41a; }
.duration-warning { color: #faad14; }
.duration-bad { color: #ff4d4f; }
```

### 3.3 JavaScript逻辑

```javascript
// static/js/performance.js

class PerformanceMonitor {
    constructor() {
        this.autoRefresh = true;
        this.refreshInterval = 5000;
        this.timer = null;
        this.frontendMetrics = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.startAutoRefresh();
        this.loadAllData();
        this.initFrontendMonitor();
    }
    
    bindEvents() {
        // Tab切换
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tab = e.target.dataset.tab;
                this.switchTab(tab);
            });
        });
        
        // 自动刷新开关
        document.getElementById('auto-refresh').addEventListener('change', (e) => {
            this.autoRefresh = e.target.checked;
            if (this.autoRefresh) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        });
    }
    
    switchTab(tab) {
        // 切换按钮状态
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        
        // 切换内容
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tab}-panel`);
        });
    }
    
    startAutoRefresh() {
        if (this.timer) return;
        this.timer = setInterval(() => this.loadAllData(), this.refreshInterval);
    }
    
    stopAutoRefresh() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }
    
    async loadAllData() {
        await Promise.all([
            this.loadApiData(),
            this.loadDbData()
        ]);
        this.updateFrontendCard();
    }
    
    async loadApiData() {
        try {
            const res = await fetch('/diag/performance');
            const data = await res.json();
            
            if (!data.enabled) {
                document.getElementById('api-status').textContent = '已禁用';
                document.getElementById('api-status').classList.add('disabled');
                return;
            }
            
            // 更新卡片
            document.getElementById('api-total').textContent = data.total_requests || 0;
            document.getElementById('api-avg').textContent = (data.duration?.avg || 0) + 'ms';
            document.getElementById('api-p95').textContent = (data.duration?.p95 || 0) + 'ms';
            
            // 计算慢请求数（>500ms）
            const slowCount = data.slow_requests?.length || 0;
            document.getElementById('api-slow').textContent = slowCount;
            
            // 更新表格
            this.updateApiTable(data.slow_requests || []);
            
        } catch (e) {
            console.error('加载API性能数据失败:', e);
        }
    }
    
    async loadDbData() {
        try {
            const res = await fetch('/diag/db');
            const data = await res.json();
            
            if (!data.enabled) {
                document.getElementById('db-status').textContent = '已禁用';
                document.getElementById('db-status').classList.add('disabled');
                return;
            }
            
            // 更新卡片
            document.getElementById('db-total').textContent = data.total_queries || 0;
            document.getElementById('db-avg').textContent = (data.duration?.avg || 0) + 'ms';
            document.getElementById('db-max').textContent = (data.duration?.max || 0) + 'ms';
            
            // 计算慢查询数
            const slowCount = data.recent_slow_queries?.length || 0;
            document.getElementById('db-slow').textContent = slowCount;
            
            // 更新表格
            this.updateDbTable(data.recent_slow_queries || []);
            
        } catch (e) {
            console.error('加载数据库数据失败:', e);
        }
    }
    
    updateApiTable(requests) {
        const tbody = document.getElementById('api-table-body');
        tbody.innerHTML = requests.slice(0, 20).map(req => `
            <tr>
                <td>${req.timestamp}</td>
                <td>${req.method}</td>
                <td>${req.path}</td>
                <td>${req.status_code}</td>
                <td class="${this.getDurationClass(req.duration_ms)}">${req.duration_ms}ms</td>
                <td>${req.db_queries}</td>
                <td>${req.redis_queries}</td>
            </tr>
        `).join('');
    }
    
    updateDbTable(queries) {
        const tbody = document.getElementById('db-table-body');
        tbody.innerHTML = queries.slice(0, 20).map(q => `
            <tr>
                <td>${q.timestamp}</td>
                <td title="${q.statement}">${q.statement.substring(0, 80)}...</td>
                <td class="${this.getDurationClass(q.duration_ms)}">${q.duration_ms}ms</td>
            </tr>
        `).join('');
    }
    
    getDurationClass(ms) {
        if (ms < 100) return 'duration-good';
        if (ms < 500) return 'duration-warning';
        return 'duration-bad';
    }
    
    // 前端性能监控
    initFrontendMonitor() {
        // 拦截XHR
        const originalXHR = window.XMLHttpRequest;
        const self = this;
        
        window.XMLHttpRequest = function() {
            const xhr = new originalXHR();
            const startTime = performance.now();
            
            xhr.addEventListener('loadend', function() {
                const duration = performance.now() - startTime;
                self.frontendMetrics.push({
                    type: 'xhr',
                    url: xhr.responseURL,
                    duration: Math.round(duration),
                    timestamp: new Date().toLocaleTimeString()
                });
                
                // 只保留最近100条
                if (self.frontendMetrics.length > 100) {
                    self.frontendMetrics.shift();
                }
                
                self.updateFrontendTable();
            });
            
            return xhr;
        };
    }
    
    updateFrontendCard() {
        const total = this.frontendMetrics.length;
        const avg = total > 0 
            ? Math.round(this.frontendMetrics.reduce((a, b) => a + b.duration, 0) / total)
            : 0;
        const max = total > 0
            ? Math.max(...this.frontendMetrics.map(m => m.duration))
            : 0;
        const xhrCount = this.frontendMetrics.filter(m => m.type === 'xhr').length;
        
        document.getElementById('fe-total').textContent = total;
        document.getElementById('fe-avg').textContent = avg + 'ms';
        document.getElementById('fe-max').textContent = max + 'ms';
        document.getElementById('fe-xhr').textContent = xhrCount;
    }
    
    updateFrontendTable() {
        const tbody = document.getElementById('fe-table-body');
        const metrics = [...this.frontendMetrics].reverse().slice(0, 20);
        
        tbody.innerHTML = metrics.map(m => `
            <tr>
                <td>${m.type.toUpperCase()}</td>
                <td title="${m.url}">${m.url.substring(0, 60)}...</td>
                <td class="${this.getDurationClass(m.duration)}">${m.duration}ms</td>
                <td>-</td>
            </tr>
        `).join('');
    }
}

// 刷新所有数据
function refreshAll() {
    monitor.loadAllData();
}

// 重置所有统计
async function resetAll() {
    if (!confirm('确定要重置所有性能统计吗？')) return;
    
    await fetch('/diag/performance/reset', {method: 'POST'});
    await fetch('/diag/db/reset', {method: 'POST'});
    
    monitor.frontendMetrics = [];
    monitor.loadAllData();
}

// 初始化
const monitor = new PerformanceMonitor();
```

---

## 四、导航栏修改

### 4.1 修改 nav.html

```html
<!-- 在报表中心后添加 -->
<a href="/performance" class="nav-item {{ 'active' if request.path == '/performance' }}">
    ⚡ 性能监控
</a>
```

### 4.2 修改 app.py 添加路由

```python
@app.route('/performance')
def performance():
    """性能监控页面"""
    return render_template('performance.html')
```

---

## 五、实施计划

### 阶段1: 创建文件（30分钟）
- [ ] `templates/performance.html` - 页面结构
- [ ] `static/css/performance.css` - 样式
- [ ] `static/js/performance.js` - 交互逻辑

### 阶段2: 修改文件（15分钟）
- [ ] `templates/nav.html` - 添加导航
- [ ] `app.py` - 添加路由

### 阶段3: 测试验证（15分钟）
- [ ] 页面正常显示
- [ ] 数据正确加载
- [ ] 自动刷新工作
- [ ] Tab切换正常

**总计: 60分钟**

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| API无数据 | 低 | 中 | 显示"暂无数据"提示 |
| 性能开销 | 低 | 低 | 5秒刷新，数据量限制 |
| 样式冲突 | 低 | 低 | 使用独立CSS类名 |

---

**文档位置**: `docs/performance_monitor_ui_design.md`

**请确认方案后实施。**
