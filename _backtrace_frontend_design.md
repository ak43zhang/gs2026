# 股债交集回溯系统 - 前端设计方案

## 1. 页面定位

**位置**: 智能选股 → 区间测算 → **股债交集回溯**（新增子导航）

**导航结构**:
```
智能选股
├── 🎯 交叉行概选股
├── 📈 涨停行概选股
├── 📊 区间测算
└── 🔍 股债交集回溯  ← 新增
```

## 2. 页面布局

### 2.1 整体结构

```
┌─────────────────────────────────────────────────────────────────┐
│  子导航栏                                                        │
│  [交叉行概] [涨停行概] [区间测算] [股债交集回溯] ← active       │
├─────────────────────────────────────────────────────────────────┤
│  面包屑：智能选股 > 股债交集回溯                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 控制面板（日期、过滤配置、操作按钮）                      │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 任务状态面板（进度、统计信息）                            │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 结果展示（表格 + 分页）                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 详细设计

#### 控制面板

```html
<div class="control-panel">
    <!-- 第一行：日期 + 操作 -->
    <div class="control-row">
        <span class="control-label">日期</span>
        <select class="control-select" id="dateSelect">
            <option value="20260803">2026-08-03（今天）</option>
            <option value="20260802">2026-08-02</option>
            <!-- 历史日期 -->
        </select>
        
        <button class="btn-query" onclick="startBacktrace()">
            🚀 开始回溯
        </button>
        <button class="btn-secondary" onclick="loadResults()">
            📋 查看结果
        </button>
    </div>
    
    <!-- 第二行：股票过滤配置 -->
    <div class="control-row">
        <span class="control-label">股票过滤</span>
        <select class="control-select" id="stockIndustry">
            <option value="">全部行业</option>
            <option value="电子">电子</option>
            <option value="银行">银行</option>
            <!-- 更多行业 -->
        </select>
        
        <select class="control-select" id="stockTopnSectors">
            <option value="0">全部行业</option>
            <option value="5">前5行业（次数）</option>
            <option value="10">前10行业（次数）</option>
        </select>
        
        <select class="control-select" id="stockTopnWindow">
            <option value="0">全部</option>
            <option value="10">前10区间次数</option>
            <option value="20">前20区间次数</option>
        </select>
        
        <label class="checkbox-label">
            <input type="checkbox" id="stockBondFilter" checked>
            仅显示有债券的
        </label>
    </div>
    
    <!-- 第三行：债券过滤配置 -->
    <div class="control-row">
        <span class="control-label">债券过滤</span>
        <select class="control-select" id="bondIndustry">
            <option value="">全部行业</option>
            <option value="电子">电子</option>
            <option value="银行">银行</option>
        </select>
        
        <select class="control-select" id="bondTopnSectors">
            <option value="0">全部行业</option>
            <option value="5">前5行业（次数）</option>
            <option value="10">前10行业（次数）</option>
        </select>
        
        <select class="control-select" id="bondTopnAmount">
            <option value="0">全部</option>
            <option value="20">前20金额</option>
            <option value="50">前50金额</option>
        </select>
        
        <label class="checkbox-label">
            <input type="checkbox" id="bondGreenFilter">
            排除绿名单
        </label>
    </div>
</div>
```

#### 任务状态面板

```html
<div class="status-panel" id="statusPanel" style="display:none;">
    <div class="status-header">
        <span class="status-title">⏳ 回溯任务执行中...</span>
        <span class="status-time" id="elapsedTime">00:00</span>
    </div>
    <div class="progress-bar">
        <div class="progress-fill" id="progressFill" style="width:0%"></div>
    </div>
    <div class="status-stats">
        <span>已处理: <b id="processedTicks">0</b> / <b id="totalTicks">0</b> ticks</span>
        <span>已发现: <b id="foundPairs">0</b> 个股债对</span>
        <span>当前时间: <b id="currentTime">--:--:--</b></span>
    </div>
</div>

<div class="result-summary" id="resultSummary" style="display:none;">
    <div class="summary-item">
        <span class="summary-label">✅ 任务完成</span>
        <span class="summary-value" id="summaryTotal">共 156 个股债对</span>
    </div>
    <div class="summary-item">
        <span class="summary-label">⏱️ 耗时</span>
        <span class="summary-value" id="summaryDuration">3分25秒</span>
    </div>
    <div class="summary-item">
        <span class="summary-label">📅 时间范围</span>
        <span class="summary-value" id="summaryRange">09:30:00 - 15:00:00</span>
    </div>
</div>
```

#### 结果展示表格

```html
<div class="result-panel">
    <div class="result-header">
        <h3>📊 回溯结果</h3>
        <div class="result-actions">
            <button class="btn-export" onclick="exportResults()">
                📥 导出Excel
            </button>
            <select class="control-select" id="pageSize" onchange="changePageSize()">
                <option value="20">20条/页</option>
                <option value="50">50条/页</option>
                <option value="100">100条/页</option>
            </select>
        </div>
    </div>
    
    <table class="result-table">
        <thead>
            <tr>
                <th>序号</th>
                <th colspan="4">股票信息</th>
                <th colspan="4">债券信息</th>
                <th>操作</th>
            </tr>
            <tr>
                <th>#</th>
                <th>代码</th>
                <th>名称</th>
                <th>涨跌幅</th>
                <th>累计次数</th>
                <th>代码</th>
                <th>名称</th>
                <th>涨跌幅</th>
                <th>金额</th>
                <th>详情</th>
            </tr>
        </thead>
        <tbody id="resultBody">
            <!-- 动态填充 -->
        </tbody>
    </table>
    
    <div class="pagination" id="pagination">
        <!-- 分页组件 -->
    </div>
</div>
```

## 3. 前端交互流程

### 3.1 启动回溯流程

```javascript
async function startBacktrace() {
    // 1. 收集配置
    const config = collectFilterConfig();
    const date = document.getElementById('dateSelect').value;
    
    // 2. 显示状态面板
    showStatusPanel();
    
    // 3. 启动定时器更新UI
    const timer = startElapsedTimer();
    
    try {
        // 4. 调用后端API
        const response = await fetch('/api/backtrace/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: date,
                filters: config
            })
        });
        
        const result = await response.json();
        
        // 5. 显示完成状态
        showCompletionStatus(result.data);
        
        // 6. 自动加载结果
        await loadResults();
        
    } catch (error) {
        showError('回溯任务失败: ' + error.message);
    } finally {
        stopTimer(timer);
    }
}
```

### 3.2 实时进度更新（WebSocket 或轮询）

```javascript
// 方案1: WebSocket 实时推送
function connectWebSocket(taskId) {
    const ws = new WebSocket(`ws://${location.host}/ws/backtrace/${taskId}`);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateProgress(data);
    };
}

// 方案2: 轮询（简单实现）
async function pollProgress(taskId) {
    const poll = setInterval(async () => {
        const response = await fetch(`/api/backtrace/task/${taskId}`);
        const data = await response.json();
        
        updateProgress(data);
        
        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(poll);
        }
    }, 1000);
}

function updateProgress(data) {
    document.getElementById('progressFill').style.width = 
        `${(data.processed_ticks / data.total_ticks) * 100}%`;
    document.getElementById('processedTicks').textContent = data.processed_ticks;
    document.getElementById('foundPairs').textContent = data.total_records;
    document.getElementById('currentTime').textContent = data.current_time || '--:--:--';
}
```

### 3.3 结果查询与分页

```javascript
async function loadResults(page = 1, pageSize = 20) {
    const date = document.getElementById('dateSelect').value;
    
    const response = await fetch(
        `/api/backtrace/results?date=${date}&page=${page}&size=${pageSize}`
    );
    
    const result = await response.json();
    
    if (result.success) {
        renderResults(result.data.records);
        renderPagination(result.data.total, page, pageSize);
    }
}

function renderResults(records) {
    const tbody = document.getElementById('resultBody');
    tbody.innerHTML = records.map((record, index) => `
        <tr>
            <td>${index + 1}</td>
            <td>${record.stock_code}</td>
            <td>${record.stock_name}</td>
            <td class="${record.stock_change_pct > 0 ? 'pct-up' : 'pct-down'}">
                ${record.stock_change_pct?.toFixed(2) || '-'}%
            </td>
            <td>${record.stock_count || '-'}</td>
            <td>${record.bond_code}</td>
            <td>${record.bond_name}</td>
            <td class="${record.bond_change_pct > 0 ? 'pct-up' : 'pct-down'}">
                ${record.bond_change_pct?.toFixed(2) || '-'}%
            </td>
            <td>${record.bond_amount?.toFixed(0) || '-'}</td>
            <td>
                <button class="btn-detail" onclick="showDetail('${record.stock_code}', '${record.bond_code}')">
                    详情
                </button>
            </td>
        </tr>
    `).join('');
}
```

## 4. 样式设计

### 4.1 新增样式（参考区间测算页面风格）

```css
/* backtrace.css */

/* 控制面板 */
.backtrace-container { max-width: 1400px; margin: 0 auto; padding: 20px; }

.control-panel {
    background: #fff; border-radius: 8px; padding: 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.control-row {
    display: flex; align-items: center; gap: 15px;
    flex-wrap: wrap; margin-bottom: 16px;
}

.control-row:last-child { margin-bottom: 0; }

.control-label {
    font-size: 14px; color: #333; font-weight: 500; min-width: 80px;
}

.control-select {
    padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px;
    font-size: 14px; background: #fff; cursor: pointer; min-width: 120px;
}

.btn-query {
    padding: 8px 24px; background: #007bff; color: #fff; border: none;
    border-radius: 6px; font-size: 14px; cursor: pointer; font-weight: 500;
}

.btn-query:hover { background: #0056b3; }

.btn-secondary {
    padding: 8px 20px; background: #6c757d; color: #fff; border: none;
    border-radius: 6px; font-size: 14px; cursor: pointer;
}

.btn-secondary:hover { background: #545b62; }

.checkbox-label {
    display: flex; align-items: center; gap: 6px;
    font-size: 14px; color: #333; cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
    width: 16px; height: 16px; cursor: pointer;
}

/* 状态面板 */
.status-panel {
    background: #fff; border-radius: 8px; padding: 20px;
    margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.status-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px;
}

.status-title { font-size: 16px; font-weight: 600; color: #007bff; }

.status-time { font-size: 14px; color: #666; font-family: monospace; }

.progress-bar {
    height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden;
    margin-bottom: 16px;
}

.progress-fill {
    height: 100%; background: linear-gradient(90deg, #007bff, #00c6ff);
    border-radius: 4px; transition: width 0.3s ease;
}

.status-stats {
    display: flex; gap: 30px; font-size: 14px; color: #666;
}

.status-stats b { color: #333; font-weight: 600; }

/* 结果摘要 */
.result-summary {
    background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px;
    padding: 16px 20px; margin-bottom: 20px; display: flex; gap: 40px;
}

.summary-item { display: flex; align-items: center; gap: 8px; }

.summary-label { font-size: 14px; color: #155724; }

.summary-value { font-size: 14px; font-weight: 600; color: #155724; }

/* 结果表格 */
.result-panel {
    background: #fff; border-radius: 8px; padding: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.result-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px;
}

.result-header h3 { font-size: 16px; font-weight: 600; color: #333; margin: 0; }

.result-actions { display: flex; gap: 10px; align-items: center; }

.btn-export {
    padding: 6px 16px; background: #28a745; color: #fff; border: none;
    border-radius: 4px; font-size: 13px; cursor: pointer;
}

.btn-export:hover { background: #218838; }

.result-table {
    width: 100%; border-collapse: collapse; font-size: 14px;
}

.result-table th, .result-table td {
    padding: 12px 16px; text-align: center; border-bottom: 1px solid #f0f0f0;
}

.result-table th {
    background: #f8f9fa; color: #666; font-weight: 500;
    position: sticky; top: 0;
}

.result-table tbody tr:hover { background: #f0f7ff; }

.result-table thead tr:first-child th {
    background: #007bff; color: #fff; font-weight: 600;
}

.pct-up { color: #e74c3c; font-weight: 600; }
.pct-down { color: #2ecc71; font-weight: 600; }

.btn-detail {
    padding: 4px 12px; background: #007bff; color: #fff; border: none;
    border-radius: 4px; font-size: 12px; cursor: pointer;
}

.btn-detail:hover { background: #0056b3; }

/* 分页 */
.pagination {
    display: flex; justify-content: center; align-items: center;
    gap: 8px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #f0f0f0;
}

.pagination button {
    padding: 6px 12px; border: 1px solid #ddd; background: #fff;
    border-radius: 4px; cursor: pointer; font-size: 13px;
}

.pagination button:hover:not(:disabled) { background: #f0f0f0; }

.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

.pagination button.active {
    background: #007bff; color: #fff; border-color: #007bff;
}

.pagination .page-info { font-size: 13px; color: #666; }
```

## 5. 文件结构

```
src/gs2026/dashboard2/
├── templates/
│   ├── stock_picker.html          # 智能选股主页面
│   ├── range_analysis.html        # 区间测算页面
│   └── backtrace.html             # 【新增】股债交集回溯页面
├── static/
│   ├── css/
│   │   └── backtrace.css          # 【新增】回溯页面样式
│   └── js/
│       └── backtrace.js           # 【新增】回溯页面逻辑
└── routes/
    ├── stock_picker.py            # 智能选股路由
    ├── range_analysis.py          # 区间测算路由
    └── backtrace.py               # 【新增】回溯路由
```

## 6. 导航集成

在 `nav.html` 和现有子导航中添加链接：

```html
<!-- nav.html -->
<a href="/stock-picker" {% if active_page == 'stock_picker' %}class="active"{% endif %}>
    智能选股
</a>

<!-- range_analysis.html 和 stock_picker.html 的子导航 -->
<div class="analysis-sub-nav">
    <a href="/stock-picker">🎯 交叉行概选股</a>
    <a href="/stock-picker#ztb">📈 涨停行概选股</a>
    <a href="/range-analysis" class="{% if active_subnav == 'range' %}active{% endif %}">
        📊 区间测算
    </a>
    <a href="/backtrace" class="{% if active_subnav == 'backtrace' %}active{% endif %}">
        🔍 股债交集回溯
    </a>
</div>
```

## 7. API 调用汇总

| 功能 | 方法 | API 路径 | 说明 |
|------|------|----------|------|
| 启动回溯 | POST | /api/backtrace/run | 启动回溯任务 |
| 查询任务 | GET | /api/backtrace/task/{id} | 获取任务进度 |
| 查询结果 | GET | /api/backtrace/results | 分页查询结果 |
| 导出结果 | GET | /api/backtrace/export | 导出 Excel |

---

请审核此前端设计方案，确认后我完善到正式文档中。
