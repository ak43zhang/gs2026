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
        bond_topn_count_mode: (document.getElementById('bondTopNCountMode') || {}).value || 'ranking'
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
        const response = await fetch('/api/backtrace/run-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: date,
                start_time: startTime,
                end_time: endTime,
                stock_config: stockConfig,
                bond_config: bondConfig
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
            showMessage(`回溯完成，共${finalData.intersection_count}个时间点有交集`, 'success');
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
    
    // 生成结果表格
    const content = document.getElementById('resultsContent');
    content.innerHTML = generateResultsHTML(data.results);
    
    document.getElementById('resultsPanel').style.display = 'block';
    document.getElementById('saveResultsBtn').disabled = false;
    
    // 更新进度为100%
    document.getElementById('progressFill').style.width = '100%';
    document.getElementById('progressText').textContent = '100%';
}

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
            html += `<td>${stock.stock_industry || '-'}</td>`;
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
            csv += `${stock.industry || ''},`;
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
