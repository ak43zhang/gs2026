/**
 * 股债交集回溯页面逻辑
 */

// 全局状态
let _currentResults = null;
let _isRunning = false;

/**
 * 初始化页面
 */
document.addEventListener('DOMContentLoaded', function() {
    initBacktracePage();
});

function initBacktracePage() {
    // 绑定事件
    document.getElementById('loadDatesBtn').addEventListener('click', loadAvailableDates);
    document.getElementById('runBacktraceBtn').addEventListener('click', runBacktrace);
    document.getElementById('saveResultsBtn').addEventListener('click', saveResults);
    document.getElementById('exportBtn').addEventListener('click', exportResults);
    document.getElementById('toggleDetailBtn').addEventListener('click', toggleAllDetails);
    
    // 加载日期列表
    loadAvailableDates();
}

/**
 * 加载可用日期列表
 */
async function loadAvailableDates() {
    const btn = document.getElementById('loadDatesBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> 加载中...';
    
    try {
        const response = await fetch('/api/backtrace/dates');
        const result = await response.json();
        
        if (result.code === 0) {
            const select = document.getElementById('dateSelect');
            select.innerHTML = '<option value="">请选择日期</option>';
            
            result.data.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = date;
                select.appendChild(option);
            });
            
            showMessage('日期列表加载成功', 'success');
        } else {
            showMessage('加载日期失败: ' + result.message, 'error');
        }
    } catch (e) {
        showMessage('加载日期失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '刷新日期';
    }
}

/**
 * 获取过滤配置
 */
function getStockConfig() {
    return {
        bond_mode: document.getElementById('stockBondFilter').checked,
        topn_industry: parseInt(document.getElementById('stockTopNIndustry').value) || 0,
        topn_industry_pct: parseInt(document.getElementById('stockTopNIndustryPct').value) || 0,
        topn_window: parseInt(document.getElementById('stockTopNWindow').value) || 0,
        topn_window_mode: (document.getElementById('stockTopNWindowMode') || {}).value || 'ranking',
        topn_count: parseInt(document.getElementById('stockTopNCount').value) || 0,
        topn_count_mode: (document.getElementById('stockTopNCountMode') || {}).value || 'ranking'
    };
}

function getBondConfig() {
    return {
        green_list: document.getElementById('bondGreenFilter').checked,
        bond_topn_industry_pct: parseInt(document.getElementById('bondTopNIndustryPct').value) || 0,
        topn_amount: parseInt(document.getElementById('bondTopNAmount').value) || 0,
        topn_amount_mode: (document.getElementById('bondTopNAmountMode') || {}).value || 'ranking',
        bond_topn_window: parseInt(document.getElementById('bondTopNWindow').value) || 0,
        bond_topn_window_mode: (document.getElementById('bondTopNWindowMode') || {}).value || 'ranking',
        bond_topn_count: parseInt(document.getElementById('bondTopNCount').value) || 0,
        bond_topn_count_mode: (document.getElementById('bondTopNCountMode') || {}).value || 'ranking',
        bond_min1_amount_topn: parseInt(document.getElementById('bondMin1AmountTopN').value) || 0,
        bond_min1_amount_topn_mode: (document.getElementById('bondMin1AmountTopNMode') || {}).value || 'ranking',
        bond_min1_change_min: parseFloat(document.getElementById('bondMin1ChangeMin').value) || 0,
        bond_min1_change_min_mode: (document.getElementById('bondMin1ChangeMinMode') || {}).value || 'ranking'
    };
}

/**
 * 执行回溯
 */
async function runBacktrace() {
    if (_isRunning) return;
    
    const date = document.getElementById('dateSelect').value;
    if (!date) {
        showMessage('请选择日期', 'error');
        return;
    }
    
    _isRunning = true;
    
    // 更新UI状态
    const btn = document.getElementById('runBacktraceBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> 回溯中...';
    
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('statusPanel').style.display = 'block';
    document.getElementById('resultsPanel').style.display = 'none';
    document.getElementById('statsPanel').style.display = 'none';
    
    try {
        const stockConfig = getStockConfig();
        const bondConfig = getBondConfig();
        const startTime = (document.getElementById('startTime') || {}).value || '';
        const endTime = (document.getElementById('endTime') || {}).value || '';

        // 使用SSE流式接口，实时显示进度
        // 启用窗口汇总模式 (aggregate=true)
        const response = await fetch('/api/backtrace/run-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: date,
                start_time: startTime,
                end_time: endTime,
                stock_config: stockConfig,
                bond_config: bondConfig,
                aggregate: true,  // 启用窗口汇总
                window_minutes: 10  // 10分钟窗口
            })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalData = null;
        let errorMsg = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // 按SSE事件分割（\n\n）
            const parts = buffer.split('\n\n');
            buffer = parts.pop();  // 最后一段可能不完整，留到下次
            for (const part of parts) {
                const line = part.trim();
                if (!line.startsWith('data:')) continue;
                let ev;
                try { ev = JSON.parse(line.slice(5).trim()); } catch (e) { continue; }

                if (ev.type === 'start') {
                    updateProgress(0, ev.total, '开始回溯...');
                } else if (ev.type === 'preload') {
                    updateProgress(0, 100, ev.msg || '预加载数据...');
                } else if (ev.type === 'progress') {
                    const pct = ev.total > 0 ? Math.round(ev.done / ev.total * 100) : 0;
                    updateProgress(pct, 100,
                        `处理中 ${ev.done}/${ev.total} tick · 批次${ev.batch}/${ev.batches} · 已找到${ev.found}个交集时点`);
                } else if (ev.type === 'done') {
                    finalData = ev.data;
                } else if (ev.type === 'error') {
                    errorMsg = ev.message;
                }
            }
        }

        if (errorMsg) {
            showMessage('回溯失败: ' + errorMsg, 'error');
        } else if (finalData) {
            _currentResults = finalData;
            displayResults(finalData);
            showMessage(`回溯完成，共${finalData.intersection_count}个时间点有交集${finalData.elapsed_seconds ? '，耗时' + finalData.elapsed_seconds + 's' : ''}`, 'success');
        } else {
            showMessage('回溯未返回结果', 'error');
        }
    } catch (e) {
        showMessage('回溯失败: ' + e.message, 'error');
    } finally {
        _isRunning = false;
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">▶️</span> 开始回溯';
    }
}

/**
 * 更新进度条
 */
function updateProgress(pct, total, text) {
    const fill = document.getElementById('progressFill');
    const ptext = document.getElementById('progressText');
    const stime = document.getElementById('statusTime');
    if (fill) fill.style.width = pct + '%';
    if (ptext) ptext.textContent = pct + '%';
    if (stime) stime.textContent = text || '';
}

/**
 * 显示结果
 * 
 * 支持两种模式:
 * 1. 传统模式: 逐tick明细展示
 * 2. 窗口汇总模式: 10分钟窗口聚合展示 (aggregate=true)
 */
function displayResults(data) {
    // 更新统计
    document.getElementById('statTotalTime').textContent = data.total_timestamps;
    document.getElementById('statIntersectionTime').textContent = data.intersection_count;
    
    const avgCount = data.intersection_count > 0 
        ? (data.results.reduce((sum, r) => sum + r.count, 0) / data.intersection_count).toFixed(1)
        : 0;
    document.getElementById('statAvgIntersection').textContent = avgCount;
    
    const maxCount = data.results.length > 0
        ? Math.max(...data.results.map(r => r.count))
        : 0;
    document.getElementById('statMaxIntersection').textContent = maxCount;
    
    document.getElementById('statsPanel').style.display = 'grid';
    
    // 非聚合模式：在结果上方追加统计面板（涨幅差/区间差分布仅在聚合模式可用）
    if (!data.aggregate_mode) {
        const el = data.elapsed_seconds ? data.elapsed_seconds + 's' : '-';
        const panel = document.createElement('div');
        panel.className = 'statistics-panel';
        panel.style.cssText = 'margin-top:16px;';
        panel.innerHTML = `
            ${statItem('回溯耗时', el)}
            ${statItem('数据模式', '逐 tick')}
        `;
        const rc = document.getElementById('resultsContent');
        if (rc) rc.insertBefore(panel, rc.firstChild);
    }
    
    // 生成结果表格
    const content = document.getElementById('resultsContent');
    
    // 判断是否启用窗口汇总模式
    if (data.aggregate_mode && data.aggregated) {
        content.innerHTML = generateWindowSummaryHTML(data.aggregated);
    } else {
        content.innerHTML = generateResultsHTML(data.results);
    }
    
    document.getElementById('resultsPanel').style.display = 'block';
    document.getElementById('saveResultsBtn').disabled = false;
    
    // 更新进度为100%
    document.getElementById('progressFill').style.width = '100%';
    document.getElementById('progressText').textContent = '100%';
}

// ==================== 10分钟窗口汇总展示功能 ====================

/**
 * 生成窗口汇总HTML
 * 使用单表头，每对占两行：第一行主信息，第二行派生指标
 */
function generateWindowSummaryHTML(aggregated) {
    if (!aggregated || !aggregated.summary || aggregated.summary.length === 0) {
        return '<div class="empty-state"><div class="empty-title">无窗口汇总数据</div></div>';
    }
    
    const { summary, statistics, windows } = aggregated;
    
    let html = '<div class="window-summary-container">';
    
    // 窗口筛选器
    html += generateWindowFilterHTML(windows, summary);
    
    // 汇总表格 - 使用统一的16列表头
    html += '<div class="summary-table-wrapper">';
    html += '<table class="summary-table">';
    html += '<thead><tr>';
    html += '<th rowspan="2">窗口</th>';           // 1
    html += '<th colspan="2">股票</th>';            // 2-3
    html += '<th colspan="2">转债</th>';            // 4-5
    html += '<th rowspan="2">行业</th>';            // 6
    html += '<th rowspan="2">次数</th>';           // 7
    html += '<th rowspan="2">最高<br>命中</th>';     // 8 (新增)
    html += '<th colspan="3">债券涨幅</th>';        // 9-11
    html += '<th rowspan="2">时间差</th>';          // 12
    html += '<th rowspan="2">涨幅差</th>';          // 13
    html += '<th rowspan="2">区间差</th>';          // 14 (新增)
    html += '<th rowspan="2">平均<br>强度</th>';     // 15
    html += '<th rowspan="2">连续度</th>';          // 16
    html += '<th rowspan="2">操作</th>';            // 17
    html += '</tr><tr>';
    html += '<th>代码</th><th>名称</th>';            // 股票代码、名称
    html += '<th>代码</th><th>名称</th>';            // 转债代码、名称
    html += '<th>开始</th><th>最高</th><th>结束</th>'; // 债券涨幅开始、最高、结束
    html += '</tr></thead>';
    html += '<tbody>';
    
    summary.forEach(windowGroup => {
        const window = windowGroup.window;
        const pairs = windowGroup.pairs || [];
        
        pairs.forEach((pair, idx) => {
            const isFirstInWindow = idx === 0;
            const rowSpan = pairs.length;
            
            // 主数据行
            html += `<tr class="summary-row" data-window="${window}" data-stock="${pair.stock_code}" data-bond="${pair.bond_code}">`;
            
            // 窗口（只在窗口内第一行显示，跨所有行）
            if (isFirstInWindow) {
                html += `<td class="window-cell" rowspan="${rowSpan}">${window}<br><span class="pair-count">${pairs.length}对</span></td>`;
            }
            
            // 股票代码+名称（分两列）
            html += `<td class="code-cell"><span class="code-tag">${pair.stock_code}</span></td>`;
            html += `<td class="name-cell">${pair.stock_name || ''}</td>`;
            
            // 转债代码+名称（分两列）
            html += `<td class="code-cell"><span class="code-tag">${pair.bond_code}</span></td>`;
            html += `<td class="name-cell">${pair.bond_name || ''}</td>`;
            
            // 行业（债券行业，与股票行业相同）
            html += `<td class="industry-cell">${pair.bond_industry || '-'}</td>`;
            
            // 出现次数
            html += `<td class="count-cell">${pair.appear_count}</td>`;
            
            // 最高命中数（新增）
            html += `<td class="max-wc-cell">${pair.max_window_count || 0}</td>`;
            
            // 债券涨幅（开始、最高、结束）- 使用 bond_change_pct
            html += `<td class="pct-cell ${getPctClass(pair.first_change_pct)}">${formatPct(pair.first_change_pct)}</td>`;
            html += `<td class="pct-cell ${getPctClass(pair.max_change_pct)}">${formatPct(pair.max_change_pct)}</td>`;
            html += `<td class="pct-cell ${getPctClass(pair.last_change_pct)}">${formatPct(pair.last_change_pct)}</td>`;
            
            // 时间差（带颜色）
            html += `<td class="time-diff-cell ${pair.time_color_class}">${pair.time_to_max_display}</td>`;
            
            // 涨幅差 - 使用三级颜色
            const gainColorClass = pair.gain_color_class || 'gain-medium';
            html += `<td class="gain-cell ${gainColorClass}">${pair.gain_to_max >= 0 ? '+' : ''}${pair.gain_to_max.toFixed(2)}%</td>`;
            
            // 区间差（结束-命中）- 复用三级颜色（<0.4含负数为绿）
            const intervalColorClass = pair.gain_interval_color_class || 'gain-medium';
            const gainInterval = (pair.gain_interval != null) ? pair.gain_interval : 0;
            html += `<td class="gain-cell ${intervalColorClass}">${gainInterval >= 0 ? '+' : ''}${gainInterval.toFixed(2)}%</td>`;
            
            // 平均强度
            html += `<td class="wc-cell">${pair.window_count_avg.toFixed(1)}</td>`;
            
            // 连续度
            html += `<td class="continuity-cell">${(pair.continuity_score * 100).toFixed(0)}%</td>`;
            
            // 操作按钮
            html += `<td class="action-cell">`;
            html += `<button class="expand-btn" onclick="togglePairDetail('${window}', '${pair.stock_code}', '${pair.bond_code}')">展开▼</button>`;
            html += `</td>`;
            
            html += '</tr>';
            
            // 展开明细行（默认隐藏，跨16列）
            html += `<tr class="detail-row" id="detail-${window}-${pair.stock_code}-${pair.bond_code}" style="display:none;">`;
            html += `<td colspan="17">`;
            html += generatePairDetailHTML(pair);
            html += `</td>`;
            html += '</tr>';
        });
    });
    
    html += '</tbody></table>';
    html += '</div>'; // summary-table-wrapper
    
    // 统计面板
    html += generateStatisticsPanelHTML(statistics);
    
    html += '</div>'; // window-summary-container
    
    return html;
}

/**
 * 生成窗口筛选器HTML
 */
function generateWindowFilterHTML(windows, summary) {
    let html = '<div class="window-filter">';
    html += '<span class="filter-label">窗口筛选:</span>';
    html += '<button class="window-btn active" data-window="all">全部</button>';
    
    summary.forEach(group => {
        const window = group.window;
        const count = group.pair_count;
        html += `<button class="window-btn" data-window="${window}">${window}<span class="count-badge">${count}</span></button>`;
    });
    
    html += '</div>';
    return html;
}

/**
 * 生成统计面板HTML
 */
function generateStatisticsPanelHTML(statistics) {
    if (!statistics) return '';
    
    const el = statistics.elapsed_seconds ? statistics.elapsed_seconds + 's' : '-';
    const gtUp = statistics.gt_up || 0, gtDown = statistics.gt_down || 0, gtMid = statistics.gt_mid || 0;
    const giUp = statistics.gi_up || 0, giDown = statistics.gi_down || 0, giMid = statistics.gi_mid || 0;
    
    let html = '<div class="statistics-panel">';
    // Row 1: 4 narrow items
    html += statItem('总窗口数', statistics.total_windows || 0);
    html += statItem('总命中对', statistics.total_pairs || 0);
    html += statItem('平均时间差', statistics.avg_time_to_max_display || '-');
    html += statItem('最大涨幅差', (statistics.max_gain >= 0 ? '+' : '') + (statistics.max_gain || 0).toFixed(2) + '%',
        statistics.max_gain >= 0 ? 'gain-up' : 'gain-down');
    // Row 2: 2 wide items
    html += colorBar('回溯耗时', el, null, 2);
    html += colorBar('涨幅差', `▲${gtUp} ▼${gtDown} ◆${gtMid}`, {up: gtUp, down: gtDown, mid: gtMid}, 2);
    // Row 3: 1 full-width item
    html += colorBar('区间差', `▲${giUp} ▼${giDown} ◆${giMid}`, {up: giUp, down: giDown, mid: giMid}, 4);
    html += '</div>';
    return html;
}

function statItem(label, value, cls) {
    return `<div class="stat-item"><span class="stat-label">${label}</span>` +
           `<span class="stat-value${cls ? ' ' + cls : ''}">${value}</span></div>`;
}

function colorBar(label, value, counts, span) {
    // counts: {up, down, mid} 或 null；span: 2 或 4
    let bar = '';
    if (counts) {
        const total = counts.up + counts.down + counts.mid;
        const upPct = total > 0 ? (counts.up / total * 100).toFixed(0) : 0;
        const downPct = total > 0 ? (counts.down / total * 100).toFixed(0) : 0;
        const midPct = total > 0 ? (counts.mid / total * 100).toFixed(0) : 0;
        bar = `<div class="color-bar"><div class="cb-seg cb-up" style="width:${upPct}%" title="涨 ${counts.up}"></div>` +
              `<div class="cb-seg cb-down" style="width:${downPct}%" title="跌 ${counts.down}"></div>` +
              `<div class="cb-seg cb-mid" style="width:${midPct}%" title="平 ${counts.mid}"></div></div>`;
        bar += `<span class="cb-legend"><span class="cb-up">▲${counts.up}</span><span class="cb-down">▼${counts.down}</span><span class="cb-mid">◆${counts.mid}</span></span>`;
    }
    return `<div class="stat-item stat-w${span}">` +
           `<span class="stat-label">${label}</span>` +
           `<span class="stat-value color-bar-wrap">${value}${bar}</span></div>`;
}

/**
 * 生成股债对明细HTML
 */
function generatePairDetailHTML(pair) {
    let html = '<div class="pair-detail">';
    
    // 头部信息
    html += '<div class="detail-header">';
    html += `<span class="detail-title">${pair.stock_code} ${pair.stock_name} / ${pair.bond_code} ${pair.bond_name}</span>`;
    html += `<span class="detail-window">窗口: ${pair.window}</span>`;
    html += '</div>';
    
    // 时间轴
    html += generateTimelineHTML(pair);
    
    // 明细表格
    html += '<div class="detail-table-wrapper">';
    html += '<table class="detail-table">';
    html += '<thead><tr>';
    html += '<th>时间</th>';
    html += '<th>债券涨幅</th>';
    html += '<th>排名</th>';
    html += '<th>window_count</th>';
    html += '<th>主力净额</th>';
    html += '<th>金额</th>';
    html += '<th>标记</th>';
    html += '</tr></thead>';
    html += '<tbody>';
    
    const details = pair.details || [];
    details.forEach(d => {
        html += '<tr>';
        html += `<td>${d.time}</td>`;
        html += `<td class="${getPctClass(d.bond_change_pct)}">${formatPct(d.bond_change_pct)}</td>`;
        html += `<td>${d.stock_rank || '-'}</td>`;
        html += `<td>${d.stock_window_count || 0}</td>`;
        html += `<td>${formatAmount(d.main_net_amount)}</td>`;
        html += `<td>${formatAmount(d.bond_amount)}</td>`;
        html += `<td>${getMarkLabel(d.mark)}</td>`;
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * 生成时间轴HTML
 */
function generateTimelineHTML(pair) {
    const details = pair.details || [];
    if (details.length === 0) return '';
    
    // 找到关键节点
    const first = details.find(d => d.mark && d.mark.includes('first'));
    const maxRecord = details.find(d => d.mark && d.mark.includes('max'));
    const last = details.find(d => d.mark && d.mark.includes('last'));
    
    let html = '<div class="timeline">';
    html += '<div class="timeline-line"></div>';
    
    // 根据出现次数决定展示模式
    if (details.length <= 5) {
        // 显示全部
        details.forEach((d, i) => {
            const isFirst = d.mark && d.mark.includes('first');
            const isMax = d.mark && d.mark.includes('max');
            const isLast = d.mark && d.mark.includes('last');
            const nodeClass = isFirst ? 'first' : (isMax ? 'max' : (isLast ? 'last' : 'normal'));
            
            html += `<div class="timeline-node ${nodeClass}">`;
            html += `<div class="node-symbol">${isFirst ? '●' : (isMax ? '★' : (isLast ? '○' : '●'))}</div>`;
            html += `<div class="node-time">${d.time}</div>`;
            html += `<div class="node-pct">${formatPct(d.bond_change_pct)}</div>`;
            html += '</div>';
        });
    } else if (details.length <= 10) {
        // 显示首次、中间2个、最高、最后
        const middle1 = details[Math.floor(details.length / 3)];
        const middle2 = details[Math.floor(details.length * 2 / 3)];
        
        html += generateTimelineNode(first, 'first');
        html += generateTimelineNode(middle1, 'normal', '...');
        html += generateTimelineNode(middle2, 'normal');
        html += generateTimelineNode(maxRecord, 'max');
        html += generateTimelineNode(last, 'last');
    } else {
        // 显示首次、最高、最后，中间省略
        html += generateTimelineNode(first, 'first');
        html += '<div class="timeline-ellipsis">...</div>';
        html += generateTimelineNode(maxRecord, 'max');
        html += '<div class="timeline-ellipsis">...</div>';
        html += generateTimelineNode(last, 'last');
    }
    
    html += '</div>';
    
    // 添加时间差和涨幅差标注
    if (first && maxRecord) {
        html += '<div class="timeline-annotation">';
        html += `<span class="time-diff ${pair.time_color_class}">⏱ ${pair.time_to_max_display}</span>`;
        html += `<span class="gain-diff ${pair.gain_to_max >= 0 ? 'gain-up' : 'gain-down'}">📈 ${pair.gain_to_max >= 0 ? '+' : ''}${pair.gain_to_max.toFixed(2)}%</span>`;
        html += '</div>';
    }
    
    return html;
}

function generateTimelineNode(record, type, label) {
    if (!record) return '';
    
    const symbols = { first: '●', max: '★', last: '○', normal: '●' };
    const labels = { first: '首次', max: '最高', last: '最后', normal: '' };
    
    let html = `<div class="timeline-node ${type}">`;
    html += `<div class="node-symbol">${symbols[type]}</div>`;
    if (label) {
        html += `<div class="node-ellipsis">${label}</div>`;
    } else {
        html += `<div class="node-time">${record.time}</div>`;
        html += `<div class="node-pct">${formatPct(record.bond_change_pct)}</div>`;
        if (labels[type]) {
            html += `<div class="node-label">${labels[type]}</div>`;
        }
    }
    html += '</div>';
    
    return html;
}

/**
 * 展开/收起股债对明细
 */
function togglePairDetail(window, stockCode, bondCode) {
    const detailId = `detail-${window}-${stockCode}-${bondCode}`;
    const detailRow = document.getElementById(detailId);
    
    if (!detailRow) return;
    
    const isHidden = detailRow.style.display === 'none';
    
    // 先收起所有其他明细
    document.querySelectorAll('.detail-row').forEach(row => {
        if (row.id !== detailId) {
            row.style.display = 'none';
        }
    });
    
    // 更新所有按钮文字
    document.querySelectorAll('.expand-btn').forEach(btn => {
        btn.textContent = '展开▼';
    });
    
    // 切换当前明细
    if (isHidden) {
        detailRow.style.display = 'table-row';
        const btn = detailRow.previousElementSibling.querySelector('.expand-btn');
        if (btn) btn.textContent = '收起▲';
    } else {
        detailRow.style.display = 'none';
    }
}

/**
 * 按窗口筛选
 */
function filterByWindow(window) {
    // 更新按钮状态
    document.querySelectorAll('.window-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.window === window) {
            btn.classList.add('active');
        }
    });
    
    // 显示/隐藏行
    document.querySelectorAll('.summary-row, .derived-row').forEach(row => {
        if (window === 'all' || row.dataset.window === window) {
            row.style.display = 'table-row';
        } else {
            row.style.display = 'none';
        }
    });
    
    // 隐藏所有明细
    document.querySelectorAll('.detail-row').forEach(row => {
        row.style.display = 'none';
    });
}

// ==================== 工具函数 ====================

function formatPct(value) {
    if (value === null || value === undefined || value === '-') return '-';
    const n = parseFloat(value);
    return isNaN(n) ? '-' : n.toFixed(2) + '%';
}

function getPctClass(value) {
    const n = parseFloat(value);
    if (isNaN(n)) return '';
    return n >= 0 ? 'change-up' : 'change-down';
}

function formatAmount(value) {
    if (value === null || value === undefined || value === 0) return '-';
    const n = parseFloat(value);
    if (isNaN(n)) return '-';
    if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (n >= 1e4) return (n / 1e4).toFixed(0) + '万';
    return n.toFixed(0);
}

function getMarkLabel(mark) {
    if (!mark) return '';
    const labels = [];
    if (mark.includes('first')) labels.push('首次');
    if (mark.includes('max')) labels.push('最高');
    if (mark.includes('last')) labels.push('最后');
    return labels.join('、');
}

// 绑定窗口筛选事件（需要在DOM加载后执行）
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('window-btn')) {
        const window = e.target.dataset.window;
        filterByWindow(window);
    }
});

/**
 * 生成结果HTML
 */
function generateResultsHTML(results) {
    if (!results || results.length === 0) {
        return '<div class="empty-state"><div class="empty-title">无交集数据</div></div>';
    }
    
    const fmtPct = (v) => {
        const n = parseFloat(v);
        return isNaN(n) ? '-' : n.toFixed(2) + '%';
    };
    const fmtAmount = (v) => {
        const n = parseFloat(v);
        if (isNaN(n) || n === 0) return '-';
        if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿';
        if (n >= 1e4) return (n / 1e4).toFixed(0) + '万';
        return n.toFixed(0);
    };
    const pctClass = (v) => {
        const n = parseFloat(v);
        return (!isNaN(n) && n >= 0) ? 'change-up' : 'change-down';
    };
    
    let html = '<table class="result-table">';
    html += '<thead><tr>';
    html += '<th>时间</th>';
    html += '<th>交集</th>';
    html += '<th>股票</th>';
    html += '<th>股涨幅</th>';
    html += '<th>行业</th>';
    html += '<th>转债</th>';
    html += '<th>债涨幅</th>';
    html += '<th>债券金额</th>';
    html += '</tr></thead>';
    html += '<tbody>';
    
    results.forEach(item => {
        const time = item.time;
        const count = item.count;
        const stocks = item.stocks || [];
        
        stocks.forEach((stock, idx) => {
            html += '<tr>';
            if (idx === 0) {
                html += `<td class="time-cell" rowspan="${count}">${time}</td>`;
                html += `<td class="count-cell" rowspan="${count}">${count}</td>`;
            }
            html += `<td><span class="code-tag">${stock.stock_code}</span> ${stock.stock_name || ''}</td>`;
            html += `<td class="${pctClass(stock.stock_change_pct)}">${fmtPct(stock.stock_change_pct)}</td>`;
            html += `<td>${stock.bond_industry || '-'}</td>`;
            html += `<td><span class="code-tag">${stock.bond_code}</span> ${stock.bond_name || ''}</td>`;
            html += `<td class="${pctClass(stock.bond_change_pct)}">${fmtPct(stock.bond_change_pct)}</td>`;
            html += `<td>${fmtAmount(stock.bond_amount)}</td>`;
            html += '</tr>';
        });
    });
    
    html += '</tbody></table>';
    return html;
}

/**
 * 保存结果
 */
async function saveResults() {
    if (!_currentResults) return;
    
    const btn = document.getElementById('saveResultsBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> 保存中...';
    
    try {
        const response = await fetch('/api/backtrace/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(_currentResults)
        });
        
        const result = await response.json();
        
        if (result.code === 0) {
            showMessage(result.message, 'success');
        } else {
            showMessage('保存失败: ' + result.message, 'error');
        }
    } catch (e) {
        showMessage('保存失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">💾</span> 保存结果';
    }
}

/**
 * 导出结果
 */
function exportResults() {
    if (!_currentResults || !_currentResults.results) return;
    
    // 构建CSV
    let csv = '时间,股票代码,股票名称,债券代码,债券名称,股票涨幅,债券涨幅,股票价格,债券价格,股票次数,债券区间次数,行业,主力净额\n';
    
    _currentResults.results.forEach(item => {
        const time = item.time;
        (item.stocks || []).forEach(stock => {
            csv += `${time},`;
            csv += `${stock.stock_code},`;
            csv += `${stock.stock_name},`;
            csv += `${stock.bond_code},`;
            csv += `${stock.bond_name},`;
            csv += `${stock.stock_change_pct || 0},`;
            csv += `${stock.bond_change_pct || 0},`;
            csv += `${stock.stock_price || 0},`;
            csv += `${stock.bond_price || 0},`;
            csv += `${stock.stock_count || 0},`;
            csv += `${stock.bond_window_count || 0},`;
            csv += `${stock.bond_industry || ''},`;
            csv += `${stock.main_net_amount || 0}\n`;
        });
    });
    
    // 下载
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `股债交集回溯_${_currentResults.date}.csv`;
    link.click();
}

/**
 * 展开/收起所有详情
 */
function toggleAllDetails() {
    const groups = document.querySelectorAll('.time-group');
    const allCollapsed = Array.from(groups).every(g => g.classList.contains('collapsed'));
    
    groups.forEach(group => {
        if (allCollapsed) {
            group.classList.remove('collapsed');
        } else {
            group.classList.add('collapsed');
        }
    });
}

/**
 * 显示消息
 */
function showMessage(message, type) {
    // 移除旧消息
    const oldMsg = document.querySelector('.message-toast');
    if (oldMsg) oldMsg.remove();
    
    // 创建新消息
    const msg = document.createElement('div');
    msg.className = `message-toast ${type}-message`;
    msg.textContent = message;
    msg.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        padding: 12px 24px;
        border-radius: 4px;
        font-size: 14px;
        animation: fadeIn 0.3s ease;
    `;
    
    document.body.appendChild(msg);
    
    // 3秒后移除
    setTimeout(() => {
        msg.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => msg.remove(), 300);
    }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }
`;
document.head.appendChild(style);
