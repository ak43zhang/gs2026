/**
 * 量化选债收益计算 - 前端实时计算逻辑
 * 
 * 使用方式：
 * 1. 获取命中记录（静态数据）
 * 2. 获取实时行情价格（WebSocket或轮询）
 * 3. 调用 calculateHitsProfit(hits, prices) 实时计算
 * 4. 展示计算结果
 */

/**
 * 实时计算所有命中记录的收益状态
 * @param {Array} hits - 命中记录列表（从后端API获取）
 * @param {Object} prices - 实时价格字典 {bond_code: current_price}
 * @param {String} currentTime - 当前时间 'HH:MM:SS'
 * @returns {Object} {hits: 计算后的记录, stats: 统计}
 */
function calculateHitsProfit(hits, prices, currentTime) {
    const currentSeconds = timeToSeconds(currentTime);
    
    const result = hits.map(hit => {
        const entryPrice = parseFloat(hit.entry_price);
        const tpPrice = parseFloat(hit.take_profit_price);
        const slPrice = parseFloat(hit.stop_loss_price);
        const maxHold = parseInt(hit.max_hold_time) || 30;
        const entrySeconds = timeToSeconds(hit.tick_time);
        
        // 已结算：直接显示最终收益
        if (hit.is_locked) {
            return {
                ...hit,
                display_return: parseFloat(hit.final_return_pct).toFixed(4),
                display_status: getStatusText(hit.lock_reason),
                display_hold_time: formatDuration(hit.hold_seconds),
                isSettled: true
            };
        }
        
        // 持仓中：实时计算
        const currentPrice = prices[hit.bond_code];
        if (!currentPrice || currentPrice <= 0) {
            return {
                ...hit,
                display_return: '--',
                display_status: '无行情',
                display_hold_time: '--',
                isSettled: false
            };
        }
        
        // 实时浮动收益
        const floatingReturn = ((currentPrice - entryPrice) / entryPrice * 100);
        const deadlineSeconds = entrySeconds + maxHold * 60;
        const holdSeconds = currentSeconds - entrySeconds;
        
        // 触发状态判断（展示用）
        let displayStatus = '持仓中';
        let statusClass = 'holding';
        
        if (currentPrice >= tpPrice) {
            displayStatus = '止盈(待确认)';
            statusClass = 'profited-pending';
        } else if (currentPrice <= slPrice) {
            displayStatus = '止损(待确认)';
            statusClass = 'stopped-pending';
        } else if (currentSeconds >= deadlineSeconds) {
            displayStatus = '超时(待确认)';
            statusClass = 'timeout-pending';
        }
        
        return {
            ...hit,
            display_return: floatingReturn.toFixed(4),
            display_status: displayStatus,
            display_status_class: statusClass,
            display_hold_time: formatDuration(holdSeconds),
            current_price: currentPrice,
            isSettled: false
        };
    });
    
    // 统计
    const stats = calculateStats(result);
    
    return { hits: result, stats };
}

/**
 * 计算统计数据
 * 
 * 盈/损统计逻辑（按用户要求）:
 * - 盈数 = 止盈触发 + (超时触发 AND 收益 >= 0)
 * - 损数 = 止损触发 + (超时触发 AND 收益 < 0)
 */
function calculateStats(hits) {
    const settled = hits.filter(h => h.isSettled);
    const holding = hits.filter(h => !h.isSettled);
    
    // 盈数：止盈 + 超时且收益>=0
    const profited = settled.filter(h => {
        if (h.lock_reason === 'take_profit') return true;
        if (h.lock_reason === 'max_time') {
            const profit = parseFloat(h.final_return_pct);
            return !isNaN(profit) && profit >= 0;
        }
        return false;
    });
    
    // 损数：止损 + 超时且收益<0
    const stopped = settled.filter(h => {
        if (h.lock_reason === 'stop_loss') return true;
        if (h.lock_reason === 'max_time') {
            const profit = parseFloat(h.final_return_pct);
            return !isNaN(profit) && profit < 0;
        }
        return false;
    });
    
    // 详细分类（用于展示）
    const takeProfitCount = settled.filter(h => h.lock_reason === 'take_profit').length;
    const stopLossCount = settled.filter(h => h.lock_reason === 'stop_loss').length;
    const timeoutProfitCount = settled.filter(h => 
        h.lock_reason === 'max_time' && parseFloat(h.final_return_pct) >= 0
    ).length;
    const timeoutLossCount = settled.filter(h => 
        h.lock_reason === 'max_time' && parseFloat(h.final_return_pct) < 0
    ).length;
    
    // 收益率统计
    const validProfits = settled
        .map(h => parseFloat(h.final_return_pct))
        .filter(p => !isNaN(p));
    
    const avgProfit = validProfits.length > 0 
        ? (validProfits.reduce((sum, p) => sum + p, 0) / validProfits.length).toFixed(4)
        : '0.0000';
    
    const totalProfit = validProfits.length > 0
        ? validProfits.reduce((sum, p) => sum + p, 0).toFixed(4)
        : '0.0000';
    
    return {
        total: hits.length,
        holding: holding.length,
        settled: settled.length,
        profited: profited.length,      // 盈总计
        stopped: stopped.length,        // 损总计
        // 详细分类
        takeProfit: takeProfitCount,    // 止盈
        stopLoss: stopLossCount,        // 止损
        timeoutProfit: timeoutProfitCount,  // 超时盈
        timeoutLoss: timeoutLossCount,      // 超时损
        // 收益率统计
        avgProfit: avgProfit,
        totalProfit: totalProfit
    };
}

/**
 * 时间转秒数
 */
function timeToSeconds(timeStr) {
    const [h, m, s] = timeStr.split(':').map(Number);
    return h * 3600 + m * 60 + s;
}

/**
 * 格式化时长
 */
function formatDuration(seconds) {
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}时${m}分`;
}

/**
 * 状态文本
 */
function getStatusText(lockReason) {
    const map = {
        'take_profit': '止盈',
        'stop_loss': '止损',
        'max_time': '超时'
    };
    return map[lockReason] || lockReason;
}

/**
 * 使用示例
 */
// 1. 获取数据
// const hits = await fetch('/api/quant_screen/hits?date=today').then(r => r.json());

// 2. 实时计算（每tick或每秒）
// setInterval(() => {
//     const prices = getRealtimePrices(); // 从WebSocket或API获取
//     const currentTime = new Date().toTimeString().slice(0, 8);
//     const { hits, stats } = calculateHitsProfit(hits, prices, currentTime);
//     
//     // 3. 更新UI
//     renderHitsTable(hits);
//     renderStats(stats);
// }, 3000);

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { calculateHitsProfit, calculateStats };
}
