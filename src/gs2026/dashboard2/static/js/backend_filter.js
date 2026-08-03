/**
 * 后端过滤切换模块
 * 
 * 支持新旧系统切换（过渡期使用）
 */

// 全局配置
let _useBackendFilter = false;  // 默认使用前端过滤

/**
 * 初始化后端过滤配置
 */
function initBackendFilter() {
    // 从localStorage读取配置
    const saved = localStorage.getItem('use_backend_filter');
    if (saved !== null) {
        _useBackendFilter = saved === 'true';
    }
    
    // 创建切换开关
    createFilterModeToggle();
    
    // 根据配置调整渲染函数
    patchRenderFunctions();
}

/**
 * 创建过滤模式切换开关
 */
function createFilterModeToggle() {
    // 查找插入位置（在过滤按钮旁边）
    const stockFilterBtn = document.getElementById('stock-filter-btn');
    const bondFilterBtn = document.getElementById('bond-filter-btn');
    
    if (stockFilterBtn) {
        const toggle = document.createElement('label');
        toggle.className = 'filter-mode-toggle';
        toggle.style.cssText = 'margin-left: 10px; cursor: pointer; font-size: 12px;';
        toggle.innerHTML = `
            <input type="checkbox" id="backend-filter-toggle" 
                   ${_useBackendFilter ? 'checked' : ''} 
                   onchange="toggleBackendFilter(this.checked)"
                   style="vertical-align: middle;">
            <span style="color: ${_useBackendFilter ? '#007bff' : '#666'};">
                ${_useBackendFilter ? '⚡后端过滤' : '前端过滤'}
            </span>
        `;
        stockFilterBtn.parentNode.insertBefore(toggle, stockFilterBtn.nextSibling);
    }
}

/**
 * 切换过滤模式
 */
function toggleBackendFilter(useBackend) {
    _useBackendFilter = useBackend;
    localStorage.setItem('use_backend_filter', useBackend);
    
    // 更新UI
    const label = document.querySelector('#backend-filter-toggle + span');
    if (label) {
        label.textContent = useBackend ? '⚡后端过滤' : '前端过滤';
        label.style.color = useBackend ? '#007bff' : '#666';
    }
    
    // 重新渲染
    rerenderStockRanking();
    rerenderBondRanking();
    
    console.log(`已切换到: ${useBackend ? '后端过滤' : '前端过滤'}`);
}

/**
 * 调用后端过滤API
 */
async function callBackendFilter(type, data, config) {
    const endpoint = type === 'stock' ? '/api/filter/stock' : '/api/filter/bond';
    
    // 【日志】记录后端过滤调用
    console.log(`[BackendFilter] 调用后端过滤: type=${type}, dataCount=${data.length}`);
    console.log(`[BackendFilter] 配置:`, JSON.stringify(config));
    
    try {
        const startTime = performance.now();
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                date: window._currentDate || getCurrentDate(),
                time: window._currentTime || getCurrentTime(),
                config: config,
                // 直接传递原始数据（用于对比验证）
                raw_data: data
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        const elapsed = performance.now() - startTime;
        
        // 【日志】记录后端过滤结果
        console.log(`[BackendFilter] 后端过滤成功: input=${data.length}, output=${result.data?.length || 0}, elapsed=${elapsed.toFixed(2)}ms`);
        
        // 记录性能
        if (result.performance) {
            console.log(`[BackendFilter] 服务端耗时: ${result.performance.elapsed_ms}ms`);
        }
        
        return result.data || [];
        
    } catch (error) {
        console.error('[BackendFilter] 后端过滤失败:', error);
        // 失败时回退到前端过滤
        return null;
    }
}

/**
 * 获取过滤配置
 */
function getStockFilterConfig() {
    return {
        stock_industry: window._selectedIndustry || null,
        stock_topn_sectors: parseInt(document.getElementById('stock-topn-industry')?.value || 0),
        stock_topn_sectors_pct: parseInt(document.getElementById('stock-topn-industry-pct')?.value || 0),
        stock_topn_window: parseInt(document.getElementById('stock-topn-window')?.value || 0),
        stock_topn_count: parseInt(document.getElementById('stock-topn-count-rank')?.value || 0),
        stock_bond_filter: window._stockBondFilterEnabled || false,
    };
}

function getBondFilterConfig() {
    return {
        bond_industry: window._selectedIndustry || null,
        bond_topn_sectors: window._bondTopNFilterEnabled ? (window._topNCount || 5) : 0,
        bond_topn_sectors_pct: parseInt(document.getElementById('bond-topn-industry-pct')?.value || 0),
        bond_topn_amount: parseInt(document.getElementById('bond-topn-amount')?.value || 0),
        bond_topn_window: parseInt(document.getElementById('bond-topn-window')?.value || 0),
        bond_topn_count: parseInt(document.getElementById('bond-topn-count-rank')?.value || 0),
        bond_green_list: window._bondGreenFilterEnabled || false,
    };
}

/**
 * 补丁：包装原有的渲染函数
 */
function patchRenderFunctions() {
    // 保存原始函数
    const originalRerenderStock = window.rerenderStockRanking;
    const originalRerenderBond = window.rerenderBondRanking;
    
    // 重写股票渲染
    window.rerenderStockRanking = async function() {
        const rawData = window._rankRawData['stock-ranking'];
        if (!rawData) {
            renderRanking('stock-ranking', []);
            updateStockFilterBadge();
            return;
        }
        
        // 显示全部模式
        if (window._showAllMode) {
            renderRanking('stock-ranking', rawData);
            updateStockFilterBadge();
            return;
        }
        
        // 交集模式
        if (window._intersectionMode) {
            window.refreshBothWithIntersection();
            return;
        }
        
        // 选择过滤方式
        let filtered;
        if (_useBackendFilter) {
            console.log('[BackendFilter] 股票过滤使用后端');
            const config = getStockFilterConfig();
            filtered = await callBackendFilter('stock', rawData, config);
            // 后端失败时回退到前端
            if (filtered === null) {
                console.warn('[BackendFilter] 后端过滤失败，回退到前端过滤');
                filtered = window.runPipeline(window.STOCK_PIPELINE, rawData);
            }
        } else {
            console.log('[BackendFilter] 股票过滤使用前端');
            filtered = window.runPipeline(window.STOCK_PIPELINE, rawData);
        }
        
        window._filteredStockData = filtered;
        renderRanking('stock-ranking', filtered);
        updateStockFilterBadge();
    };
    
    // 重写债券渲染
    window.rerenderBondRanking = async function() {
        const rawData = window._rankRawData['bond-ranking'];
        if (!rawData) {
            renderRanking('bond-ranking', []);
            updateBondFilterBadge();
            return;
        }
        
        window._bondRankRawData = [...rawData];
        
        if (window._showAllMode) {
            renderRanking('bond-ranking', rawData);
            updateBondFilterBadge();
            return;
        }
        
        if (window._intersectionMode) {
            window.refreshBothWithIntersection();
            return;
        }
        
        let filtered;
        if (_useBackendFilter) {
            console.log('[BackendFilter] 债券过滤使用后端');
            const config = getBondFilterConfig();
            filtered = await callBackendFilter('bond', rawData, config);
            if (filtered === null) {
                console.warn('[BackendFilter] 后端过滤失败，回退到前端过滤');
                filtered = window.runPipeline(window.BOND_PIPELINE, rawData);
            }
        } else {
            console.log('[BackendFilter] 债券过滤使用前端');
            filtered = window.runPipeline(window.BOND_PIPELINE, rawData);
        }
        
        window._filteredBondData = filtered;
        renderRanking('bond-ranking', filtered);
        updateBondFilterBadge();
    };
}

/**
 * 导出过滤结果（用于对比验证）
 */
function exportFilterResult(type) {
    const data = type === 'stock' 
        ? window._filteredStockData 
        : window._filteredBondData;
    
    if (!data) {
        console.warn('没有过滤结果可导出');
        return;
    }
    
    const jsonStr = JSON.stringify(data, null, 2);
    
    // 复制到剪贴板
    navigator.clipboard.writeText(jsonStr).then(() => {
        console.log(`${type}过滤结果已复制到剪贴板`);
        alert(`${type}过滤结果已复制，请粘贴保存为 ${type}_frontend.json`);
    }).catch(err => {
        console.error('复制失败:', err);
        // 降级：创建下载
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${type}_frontend.json`;
        a.click();
        URL.revokeObjectURL(url);
    });
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', initBackendFilter);

// 导出到全局
window.toggleBackendFilter = toggleBackendFilter;
window.exportFilterResult = exportFilterResult;
window.getStockFilterConfig = getStockFilterConfig;
window.getBondFilterConfig = getBondFilterConfig;
