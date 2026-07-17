# 买点候选回溯功能 - 完整设计方案

## 功能概述

修改买点候选条件后，用**新条件**重新计算**指定日期范围**的历史买点候选数据，完整替换旧数据。异步执行，实时进度，不影响其他功能。

---

## 一、完整用户操作流程

```
[1] 点击 ⚙ 打开条件编辑器
    │
    ▼
[2] 修改条件（开关/参数/模式）
    │
    ▼
[3] 点击 [保存条件] → localStorage + 实时数据立即生效
    │
    ▼
[4] 点击 [🔄回溯历史] → 展开回溯配置区
    │
    ▼
[5] 选择日期范围（日期选择器：开始日期 ~ 结束日期）
    │
    ▼
[6] 点击 [查询时间点] → 调用API获取每天的时间点数量
    │       返回: {20260522: 238, 20260521: 240, total: 478}
    │
    ▼
[7] 确认后点击 [开始回溯] → POST /api/monitor/buy-points/backtest
    │
    ▼
[8] 查看实时进度条（████████░░ 80%  处理中: 20260522 10:30:00）
    │
    ▼
[9] 完成 → 自动刷新近期记录
```

---

## 二、前端位置与UI设计

### 2.1 按钮位置

在条件编辑器弹窗底部，"保存条件"和"重置默认"旁边新增"🔄回溯历史"按钮。

### 2.2 条件编辑器弹窗布局

```
┌────────────────────────────────────────┐
│  条件设置                          [×]   │
│                                        │
│  大盘条件                               │
│  ☑ 股票红柱>涨家数                       │
│  ☑ 股票tick比 > [1.0]                   │
│  ...                                   │
│                                        │
│  个股条件                               │
│  ☑ 主力/峰值 > [0.9]    [必要▼]          │
│  ...                                   │
│                                        │
│  联动条件                               │
│  ☑ 债券在排行            [加分▼]          │
│  ☐ 绿名单(内)           [必要▼]          │
│  ☐ 绿名单(外)           [必要▼]          │
│                                        │
│  ┌──────────────────────────────────┐   │
│  │ [保存条件] [重置默认] [🔄回溯历史] │   │
│  └──────────────────────────────────┘   │
│                                        │
│  ┌──────────────────────────────────┐   │  ← 点击"回溯历史"后展开
│  │ 🔄 回溯配置                        │   │
│  │                                    │   │
│  │ 开始日期: [2026-05-20] 📅           │   │  ← 日期选择器
│  │ 结束日期: [2026-05-22] 📅           │   │  ← 日期选择器
│  │                                    │   │
│  │ [查询时间点]                        │   │  ← 先查询再执行
│  │                                    │   │
│  │ 时间点统计:                         │   │  ← 查询结果
│  │   2026-05-20: 240 个时间点          │   │
│  │   2026-05-21: 238 个时间点          │   │
│  │   2026-05-22: 235 个时间点          │   │
│  │   合计: 713 个时间点                │   │
│  │                                    │   │
│  │ ████████████░░░░ 45%               │   │  ← 进度条（回溯时显示）
│  │ 处理中: 20260522 10:30:00          │   │
│  │                                    │   │
│  │         [开始回溯]  [取消]          │   │
│  └──────────────────────────────────┘   │
└────────────────────────────────────────┘
```

### 2.3 HTML改动（monitor.html 第2884行）

```html
<!-- 当前代码 -->
<div class="bp-editor-actions">
    <button onclick="saveBpConfig()">保存条件</button>
    <button onclick="resetBpConfig()" class="bp-btn-secondary">重置默认</button>
</div>

<!-- 改为 -->
<div class="bp-editor-actions">
    <button onclick="saveBpConfig()">保存条件</button>
    <button onclick="resetBpConfig()" class="bp-btn-secondary">重置默认</button>
    <button onclick="toggleBacktestPanel()" class="bp-btn-backtest">🔄 回溯历史</button>
</div>

<!-- 新增回溯配置区 -->
<div id="bp-backtest-section" style="display:none;border-top:1px solid #eee;padding-top:8px;margin-top:8px;">
    <div class="bp-editor-title">🔄 回溯配置</div>
    <div style="display:flex;gap:8px;align-items:center;margin:6px 0;">
        <label style="font-size:12px;">开始日期:</label>
        <input type="date" id="backtest-start-date" style="font-size:12px;padding:2px 6px;border:1px solid #ddd;border-radius:3px;">
        <label style="font-size:12px;">结束日期:</label>
        <input type="date" id="backtest-end-date" style="font-size:12px;padding:2px 6px;border:1px solid #ddd;border-radius:3px;">
    </div>
    <button onclick="queryBacktestTimepoints()" style="padding:3px 10px;font-size:12px;border:1px solid #667eea;color:#667eea;background:#fff;border-radius:4px;cursor:pointer;">查询时间点</button>
    <div id="backtest-timepoints-info" style="display:none;margin-top:6px;font-size:12px;color:#555;background:#f8f9fa;padding:6px 8px;border-radius:4px;"></div>
    <div id="backtest-progress-area" style="display:none;margin-top:8px;">
        <div style="background:#f0f0f0;border-radius:10px;height:16px;overflow:hidden;">
            <div id="backtest-progress-fill" style="height:100%;background:linear-gradient(90deg,#667eea,#764ba2);width:0%;transition:width 0.3s;"></div>
        </div>
        <div id="backtest-progress-text" style="font-size:11px;color:#666;margin-top:4px;text-align:center;">准备中...</div>
    </div>
    <div style="margin-top:8px;display:flex;gap:8px;">
        <button id="btn-start-backtest" onclick="startBacktest()" disabled style="padding:4px 12px;border:none;border-radius:4px;font-size:12px;cursor:pointer;background:#ccc;color:#fff;">开始回溯</button>
        <button onclick="toggleBacktestPanel()" class="bp-btn-secondary" style="padding:4px 12px;font-size:12px;">取消</button>
    </div>
</div>
```

---

## 三、后端API设计

### 3.1 查询时间点数量

```http
POST /api/monitor/buy-points/backtest/query-timepoints
Content-Type: application/json

{
    "start_date": "20260520",
    "end_date": "20260522"
}

Response:
{
    "success": true,
    "dates": {
        "20260520": {"count": 240, "first": "09:30:00", "last": "14:57:00"},
        "20260521": {"count": 238, "first": "09:30:00", "last": "14:57:00"},
        "20260522": {"count": 235, "first": "09:30:00", "last": "14:57:00"}
    },
    "total_points": 713,
    "total_days": 3
}
```

### 3.2 启动回溯

```http
POST /api/monitor/buy-points/backtest
Content-Type: application/json

{
    "start_date": "20260520",
    "end_date": "20260522",
    "conditions": {
        "_on_body_gt_cur": true,
        "_on_tick_ratio": true,
        "tick_min": 1.5,
        "_on_green_bond_in": true,
        "_mode_green_bond_in": "required",
        ...
    }
}

Response:
{
    "success": true,
    "task_id": "a1b2c3d4",
    "message": "回溯任务已启动，3天共713个时间点",
    "dates": ["20260520", "20260521", "20260522"],
    "total_points": 713
}
```

### 3.3 查询进度

```http
GET /api/monitor/buy-points/backtest/status?task_id=a1b2c3d4

Response:
{
    "success": true,
    "task_id": "a1b2c3d4",
    "status": "running",
    "progress": 0.45,
    "current_date": "20260521",
    "current_time": "10:30:00",
    "processed": 350,
    "total": 713,
    "error": null,
    "result": null
}
```

---

## 四、后端核心实现

### 4.1 性能优化：批量处理

**核心优化思路**：不是逐个股票查询，而是**按时间点批量获取整个排行**，一次性评估所有股票。

```
旧方案（慢）：
  for each 时间点:
    for each 股票:           ← 逐个股票查询
      查询涨跌幅
      查询主力净额
      评估条件

新方案（快）：
  for each 日期:
    预加载绿名单/红名单       ← 只加载1次
    for each 时间点:
      批量获取股票排行         ← 1次查询返回所有股票
      批量获取债券排行         ← 1次查询
      批量获取行业排行         ← 1次查询
      批量获取大盘数据         ← 1次查询
      批量enrichment          ← 批量添加债券映射+涨跌幅+主力净额
      遍历股票评估条件         ← 纯内存计算，无IO
      批量保存结果             ← 1次批量INSERT
```

### 4.2 单时间点处理流程

```python
def _process_single_timepoint(self, date, time_str, conditions, green_bond_set, red_list_set):
    """处理单个时间点（复用现有API逻辑）"""
    
    # 1. 批量获取排行数据（复用DataService）
    stock_ranking = data_service.get_ranking_at_time('stock', limit=200, date=date, time_str=time_str)
    bond_ranking = data_service.get_ranking_at_time('bond', limit=100, date=date, time_str=time_str)
    industry_ranking = data_service.get_ranking_at_time('industry', limit=30, date=date, time_str=time_str)
    
    # 2. 批量enrichment（复用_enrich_stock_data + _enrich_change_pct_and_main_net）
    stock_ranking = _enrich_stock_data(stock_ranking)           # 批量添加债券映射+绿名单标记
    stock_ranking = _enrich_change_pct_and_main_net(stock_ranking, date, time_str)  # 批量添加涨跌幅+主力净额
    
    # 3. 批量获取大盘数据
    market_data = data_service.get_market_stats(date=date, time_str=time_str)
    
    # 4. 构建上下文（纯内存）
    bond_set = set(b['code'] for b in bond_ranking if b.get('code'))
    bond_map = {b['code']: b for b in bond_ranking if b.get('code')}
    ind_top = int(conditions.get('ind_top', 10))
    top_ind = set(i['name'] for i in industry_ranking[:ind_top] if i.get('name'))
    ctx = {'bondSet': bond_set, 'bondMap': bond_map, 'topInd': top_ind}
    
    # 5. 评估所有股票（纯内存计算，无IO）
    candidates = []
    for stock in stock_ranking:
        result = self._evaluate_stock(stock, conditions, ctx, market_data)
        if result:
            candidates.append(result)
    
    # 6. 排序取前30
    candidates.sort(key=lambda x: (-x['level'], -x['score']))
    candidates = candidates[:30]
    
    return candidates, market_context
```

### 4.3 性能对比

| 操作 | 旧方案 | 新方案 | 提升 |
|------|--------|--------|------|
| 获取股票数据 | N次查询(N=股票数) | 1次批量查询 | 60-200x |
| 获取债券映射 | N次查询 | 1次批量查询 | 60-200x |
| 获取涨跌幅 | N次查询 | 1次批量查询 | 60-200x |
| 绿名单/红名单 | 每时间点加载 | 每日期加载1次 | 240x |
| 条件评估 | 无变化（纯内存） | 无变化（纯内存） | 1x |

**预估耗时**（单日240个时间点）：
- 每时间点：~200ms（1次股票查询 + 1次债券查询 + 1次行业查询 + 1次enrichment + 内存计算）
- 单日总耗时：~48秒
- 3天总耗时：~2.5分钟

### 4.4 数据替换策略

```python
def _replace_data(self, engine, dates, temp_table):
    """事务替换：删除旧数据 → 插入新数据"""
    from sqlalchemy import text
    
    with engine.begin() as conn:
        for date in dates:
            save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            conn.execute(text("DELETE FROM buy_point_candidates WHERE date = :d"), {'d': save_date})
        
        conn.execute(text(f"INSERT INTO buy_point_candidates SELECT * FROM {temp_table}"))
    
    # 清理临时表
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
        conn.commit()
```

---

## 五、前端JavaScript实现

### 5.1 核心函数

```javascript
// 切换回溯面板
function toggleBacktestPanel() {
    var section = document.getElementById('bp-backtest-section');
    if (section.style.display === 'none') {
        section.style.display = 'block';
        resetBacktestUI();
        // 默认日期：最近3个交易日
        var today = new Date();
        var end = today.toISOString().split('T')[0];
        document.getElementById('backtest-end-date').value = end;
        var start = new Date(today);
        start.setDate(start.getDate() - 5);  // 往前5天确保覆盖3个交易日
        document.getElementById('backtest-start-date').value = start.toISOString().split('T')[0];
    } else {
        section.style.display = 'none';
    }
}

// 查询时间点数量
async function queryBacktestTimepoints() {
    var startDate = document.getElementById('backtest-start-date').value.replace(/-/g, '');
    var endDate = document.getElementById('backtest-end-date').value.replace(/-/g, '');
    if (!startDate || !endDate) { alert('请选择日期范围'); return; }
    
    try {
        var response = await fetch('/api/monitor/buy-points/backtest/query-timepoints', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({start_date: startDate, end_date: endDate})
        });
        var result = await response.json();
        
        if (!result.success) throw new Error(result.message);
        
        // 显示时间点统计
        var info = document.getElementById('backtest-timepoints-info');
        info.style.display = 'block';
        var html = '';
        for (var date in result.dates) {
            var d = result.dates[date];
            html += date + ': ' + d.count + ' 个时间点 (' + d.first + ' ~ ' + d.last + ')<br>';
        }
        html += '<b>合计: ' + result.total_points + ' 个时间点, ' + result.total_days + ' 天</b>';
        info.innerHTML = html;
        
        // 启用开始按钮
        var btn = document.getElementById('btn-start-backtest');
        btn.disabled = false;
        btn.style.background = '#667eea';
        btn.textContent = '开始回溯';
        
        // 缓存查询结果
        window._backtestDates = Object.keys(result.dates);
        window._backtestTotalPoints = result.total_points;
        
    } catch (e) {
        alert('查询失败: ' + e.message);
    }
}

// 启动回溯
async function startBacktest() {
    if (!window._backtestDates || window._backtestDates.length === 0) {
        alert('请先查询时间点'); return;
    }
    
    var btn = document.getElementById('btn-start-backtest');
    btn.disabled = true;
    btn.textContent = '回溯中...';
    
    document.getElementById('backtest-progress-area').style.display = 'block';
    
    try {
        var startDate = document.getElementById('backtest-start-date').value.replace(/-/g, '');
        var endDate = document.getElementById('backtest-end-date').value.replace(/-/g, '');
        
        var response = await fetch('/api/monitor/buy-points/backtest', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                start_date: startDate,
                end_date: endDate,
                conditions: _bpParams
            })
        });
        var result = await response.json();
        if (!result.success) throw new Error(result.message);
        
        window._backtestTaskId = result.task_id;
        startBacktestPolling();
    } catch (e) {
        btn.disabled = false;
        btn.textContent = '重试';
        btn.style.background = '#667eea';
        document.getElementById('backtest-progress-text').textContent = '启动失败: ' + e.message;
    }
}

// 轮询进度
function startBacktestPolling() {
    if (window._backtestPollTimer) clearInterval(window._backtestPollTimer);
    window._backtestPollTimer = setInterval(pollBacktestStatus, 1000);
}

async function pollBacktestStatus() {
    if (!window._backtestTaskId) return;
    try {
        var r = await (await fetch('/api/monitor/buy-points/backtest/status?task_id=' + window._backtestTaskId)).json();
        if (!r.success) return;
        
        var pct = Math.round(r.progress * 100);
        document.getElementById('backtest-progress-fill').style.width = pct + '%';
        document.getElementById('backtest-progress-text').textContent = 
            '处理中: ' + r.processed + '/' + r.total + ' (' + pct + '%) - ' + r.current_date + ' ' + r.current_time;
        
        if (r.status === 'completed') {
            clearInterval(window._backtestPollTimer);
            document.getElementById('backtest-progress-text').textContent = 
                '✓ 回溯完成! 共处理 ' + r.total + ' 个时间点, 生成 ' + (r.result.total_candidates || 0) + ' 条记录';
            document.getElementById('backtest-progress-fill').style.background = '#4caf50';
            document.getElementById('btn-start-backtest').textContent = '✓ 完成';
            setTimeout(function() { loadRecentBuyPoints(); }, 1000);
        } else if (r.status === 'failed') {
            clearInterval(window._backtestPollTimer);
            document.getElementById('backtest-progress-text').textContent = '✗ 失败: ' + r.error;
            document.getElementById('backtest-progress-fill').style.background = '#e57373';
            var btn = document.getElementById('btn-start-backtest');
            btn.disabled = false; btn.textContent = '重试'; btn.style.background = '#667eea';
        }
    } catch (e) { console.error('[BACKTEST] poll error:', e); }
}

function resetBacktestUI() {
    document.getElementById('backtest-timepoints-info').style.display = 'none';
    document.getElementById('backtest-progress-area').style.display = 'none';
    document.getElementById('backtest-progress-fill').style.width = '0%';
    document.getElementById('backtest-progress-fill').style.background = 'linear-gradient(90deg,#667eea,#764ba2)';
    document.getElementById('backtest-progress-text').textContent = '准备中...';
    document.getElementById('btn-start-backtest').disabled = true;
    document.getElementById('btn-start-backtest').style.background = '#ccc';
    document.getElementById('btn-start-backtest').textContent = '开始回溯';
    window._backtestDates = null;
    window._backtestTotalPoints = 0;
}
```

---

## 六、条件定义（后端复刻前端）

后端需要复刻前端 `BP_CONDITIONS` 的所有条件。完整条件列表：

### 大盘条件 (type=market)

| id | name | param | default | 逻辑 |
|----|------|-------|---------|------|
| body_gt_cur | 股票红柱>涨家数 | - | - | stock.body_up > stock.cur_up |
| tick_ratio | 股票tick比 | tick_min | 1.0 | stock.min_up / stock.min_down > p |
| strength | 股票强度 | str_min | 50 | stock.strength_score > p |
| bond_body_gt_cur | 债券红柱>涨家数 | - | - | bond.body_up > bond.cur_up |
| bond_tick_ratio | 债券tick比 | btick_min | 1.0 | bond.min_up / bond.min_down > p |
| stock_ud_ratio | 股票涨跌比 | sud_min | 0.8 | stock.cur_up / stock.cur_down > p |
| stock_body_ratio | 股票红绿柱比 | sbody_min | 0.8 | stock.body_up / stock.body_down > p |
| bond_ud_ratio | 债券涨跌比 | bud_min | 0.8 | bond.cur_up / bond.cur_down > p |
| bond_body_ratio | 债券红绿柱比 | bbody_min | 0.8 | bond.body_up / bond.body_down > p |

### 个股条件 (type=stock)

| id | name | param | default | mode | 逻辑 |
|----|------|-------|---------|------|------|
| net_ratio | 主力/峰值 | net_min | 0.9 | required | cumulative_main_net / max_cumulative_main_net > p |
| change_pct | 涨幅% | chg_min | 2 | required | change_pct > p |
| in_top_ind | 行业前N | ind_top | 10 | bonus | industry_name in topInd |
| consec_attack | 连续上攻>0 | - | - | required | consecutive_attacks > 0 |

### 联动条件 (type=link)

| id | name | param | default | mode | 逻辑 |
|----|------|-------|---------|------|------|
| bond_in_rank | 债券在排行 | - | - | bonus | bond_code in bondSet |
| bond_chg | 债券涨幅 | bchg_min | 2 | bonus | bondMap[bond_code].change_pct > p |
| green_bond_in | 绿名单(内) | - | - | required | is_green_bond == True |
| green_bond_out | 绿名单(外) | - | - | required | is_green_bond != True |

---

## 七、风险分析

### 7.1 数据准确性风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| **Redis历史数据已过期** | 查不到某时间点数据 | DataService已有MySQL回退机制 |
| **MySQL数据不完整** | 某些表缺少数据 | 跳过缺失时间点，在结果中标记 |
| **绿名单日期不匹配** | 错误标记is_green_bond | 每个日期预加载对应日期的绿名单缓存 |
| **前后端条件逻辑不一致** | 回溯结果与实时不同 | 严格复刻，增加测试对比 |

### 7.2 性能风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| **时间点过多** | 处理时间过长 | 前端显示时间点数让用户确认 |
| **MySQL查询压力** | 影响实时服务 | 线程池限制并发(max_workers=2) |
| **临时表过大** | 磁盘/内存压力 | 批量INSERT，及时清理 |
| **事务锁竞争** | 阻塞实时写入 | 短事务，分批删除 |

### 7.3 薄弱点

| 薄弱点 | 说明 | 建议 |
|--------|------|------|
| **DataService.get_ranking_at_time** | 每次查询MySQL做GROUP BY | 未来可考虑预计算结果缓存 |
| **_enrich_change_pct_and_main_net** | 每时间点单独查询 | 已是批量查询，可接受 |
| **大盘数据获取** | get_market_stats 可能查询较慢 | 已有Redis缓存机制 |

---

## 八、改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `routes/backtest_worker.py` | **新建** | 回溯任务管理器 + 核心计算逻辑 (~300行) |
| `routes/monitor.py` | **修改** | 新增3个API路由 (~80行) |
| `templates/monitor.html` | **修改** | HTML回溯配置区 + CSS样式 + JS交互逻辑 (~200行) |

---

*文档版本: 2.0*
*最后更新: 2026-05-24*
