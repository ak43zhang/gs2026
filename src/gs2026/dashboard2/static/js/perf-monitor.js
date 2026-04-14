/**
 * 前端性能监控器 - 非侵入式
 * 
 * 使用方法:
 * 1. 在 settings.yaml 中启用: frontend_perf.enabled: true
 * 2. 或通过URL参数启用: ?perf_monitor=1
 * 3. 禁用: <script>window.DISABLE_PERF_MONITOR = true;</script>
 * 
 * 特性:
 * - 零侵入: 不修改现有页面代码
 * - 可插拔: 通过 settings.yaml 或URL参数控制
 * - 低开销: 只记录最近100条请求
 */

(function() {
    'use strict';
    
    // 全局配置（由后端注入）
    const globalConfig = window.FRONTEND_PERF_CONFIG || { enabled: false };
    
    // 检查是否通过URL参数启用
    const urlParams = new URLSearchParams(window.location.search);
    const enabledByUrl = urlParams.get('perf_monitor') === '1';
    
    // 检查是否被禁用
    if (window.DISABLE_PERF_MONITOR) {
        console.log('[PerfMonitor] 已通过全局变量禁用');
        return;
    }
    
    // 启用条件：settings.yaml中启用 或 URL参数启用
    const shouldEnable = globalConfig.enabled || enabledByUrl;
    
    if (!shouldEnable) {
        console.log('[PerfMonitor] 未启用（在settings.yaml中设置 frontend_perf.enabled: true 或添加 ?perf_monitor=1 到URL）');
        return;
    }
    
    const PerfMonitor = {
        enabled: true,
        metrics: [],
        maxMetrics: globalConfig.max_metrics || 100,
        showPanelShortcut: globalConfig.show_panel_shortcut !== false,
        
        init() {
            this.hookXHR();
            this.hookFetch();
            this.observeResources();
            console.log('[PerfMonitor] 已启用（按 Ctrl+Shift+P 显示面板）');
        },
        
        // 拦截XMLHttpRequest
        hookXHR() {
            const originalXHR = window.XMLHttpRequest;
            const self = this;
            
            window.XMLHttpRequest = function() {
                const xhr = new originalXHR();
                const startTime = performance.now();
                
                xhr.addEventListener('loadend', function() {
                    const duration = performance.now() - startTime;
                    self.recordMetric({
                        type: 'xhr',
                        url: xhr.responseURL || xhr._url || 'unknown',
                        method: xhr._method || 'GET',
                        duration: Math.round(duration),
                        status: xhr.status,
                        size: xhr.responseText?.length || 0,
                    });
                });
                
                // 保存method和url
                const originalOpen = xhr.open;
                xhr.open = function(method, url, ...args) {
                    xhr._method = method;
                    xhr._url = url;
                    return originalOpen.apply(this, [method, url, ...args]);
                };
                
                return xhr;
            };
        },
        
        // 拦截Fetch API
        hookFetch() {
            const originalFetch = window.fetch;
            const self = this;
            
            window.fetch = function(...args) {
                const startTime = performance.now();
                const url = args[0];
                const options = args[1] || {};
                
                return originalFetch.apply(this, args).then(response => {
                    const duration = performance.now() - startTime;
                    self.recordMetric({
                        type: 'fetch',
                        url: url,
                        method: options.method || 'GET',
                        duration: Math.round(duration),
                        status: response.status,
                    });
                    return response;
                }).catch(error => {
                    const duration = performance.now() - startTime;
                    self.recordMetric({
                        type: 'fetch',
                        url: url,
                        method: options.method || 'GET',
                        duration: Math.round(duration),
                        status: 0,
                        error: error.message,
                    });
                    throw error;
                });
            };
        },
        
        // 观察资源加载
        observeResources() {
            if (!window.PerformanceObserver) return;
            
            const self = this;
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.entryType === 'resource') {
                        // 只记录API请求，排除静态资源
                        const isApiRequest = entry.name.includes('/api/') || 
                                            entry.name.includes('/diag/');
                        if (isApiRequest) {
                            self.recordMetric({
                                type: 'resource',
                                url: entry.name,
                                duration: Math.round(entry.duration),
                                size: entry.transferSize,
                            });
                        }
                    }
                }
            });
            
            try {
                observer.observe({ entryTypes: ['resource'] });
            } catch (e) {
                console.warn('[PerfMonitor] PerformanceObserver 不支持 resource 类型');
            }
        },
        
        // 记录指标
        recordMetric(metric) {
            metric.timestamp = new Date().toISOString();
            this.metrics.push(metric);
            
            if (this.metrics.length > this.maxMetrics) {
                this.metrics.shift();
            }
            
            // 慢请求警告（>500ms）
            if (metric.duration > 500) {
                console.warn(`[PerfMonitor] 慢请求: ${metric.url} | ${metric.duration}ms`);
            }
        },
        
        // 获取统计
        getStats() {
            if (this.metrics.length === 0) {
                return { message: '暂无数据' };
            }
            
            const durations = this.metrics.map(m => m.duration);
            const byType = {};
            
            this.metrics.forEach(m => {
                if (!byType[m.type]) {
                    byType[m.type] = { count: 0, total: 0, max: 0 };
                }
                byType[m.type].count++;
                byType[m.type].total += m.duration;
                byType[m.type].max = Math.max(byType[m.type].max, m.duration);
            });
            
            // 计算P95
            const sortedDurations = [...durations].sort((a, b) => a - b);
            const p95Idx = Math.floor(sortedDurations.length * 0.95);
            const p95 = sortedDurations[p95Idx];
            
            return {
                total: this.metrics.length,
                duration: {
                    avg: Math.round(durations.reduce((a, b) => a + b, 0) / durations.length),
                    min: Math.min(...durations),
                    max: Math.max(...durations),
                    p95: p95,
                },
                byType: Object.entries(byType).map(([type, stats]) => ({
                    type,
                    count: stats.count,
                    avg: Math.round(stats.total / stats.count),
                    max: stats.max,
                })),
                slowest: this.metrics
                    .filter(m => m.duration > 500)
                    .sort((a, b) => b.duration - a.duration)
                    .slice(0, 10),
            };
        },
        
        // 显示面板
        showPanel() {
            const stats = this.getStats();
            console.log('[PerfMonitor] 性能统计:', stats);
            
            // 创建或更新浮动面板
            let panel = document.getElementById('perf-monitor-panel');
            if (!panel) {
                panel = document.createElement('div');
                panel.id = 'perf-monitor-panel';
                panel.style.cssText = `
                    position: fixed;
                    bottom: 10px;
                    right: 10px;
                    background: rgba(0,0,0,0.85);
                    color: #0f0;
                    padding: 15px;
                    border-radius: 8px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                    z-index: 9999;
                    max-width: 350px;
                    max-height: 400px;
                    overflow-y: auto;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                `;
                document.body.appendChild(panel);
            }
            
            if (stats.message) {
                panel.innerHTML = `
                    <div style="font-weight:bold;margin-bottom:8px;color:#fff;">⚡ 性能监控</div>
                    <div style="color:#888;">${stats.message}</div>
                `;
            } else {
                const byTypeHtml = stats.byType.map(t => 
                    `<div style="margin-left:10px;color:#aaa;">${t.type}: ${t.count}次, 平均${t.avg}ms, 最大${t.max}ms</div>`
                ).join('');
                
                const slowestHtml = stats.slowest.length > 0 
                    ? `<div style="margin-top:10px;color:#f44;">慢请求 (>500ms): ${stats.slowest.length}个</div>`
                    : '';
                
                panel.innerHTML = `
                    <div style="font-weight:bold;margin-bottom:8px;color:#fff;">⚡ 性能监控</div>
                    <div style="color:#0f0;">总请求: ${stats.total}</div>
                    <div style="color:#0f0;">平均: ${stats.duration.avg}ms | 最大: ${stats.duration.max}ms | P95: ${stats.duration.p95}ms</div>
                    <div style="margin-top:8px;color:#fff;">按类型:</div>
                    ${byTypeHtml}
                    ${slowestHtml}
                    <div style="margin-top:10px;font-size:10px;color:#666;border-top:1px solid #333;padding-top:8px;">
                        按 F12 → Console 查看详情<br>
                        按 Ctrl+Shift+P 切换此面板
                    </div>
                `;
            }
            
            // 点击面板关闭
            panel.onclick = function() {
                panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
            };
        },
        
        // 重置数据
        reset() {
            this.metrics = [];
            console.log('[PerfMonitor] 数据已重置');
        }
    };
    
    // 自动初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => PerfMonitor.init());
    } else {
        PerfMonitor.init();
    }
    
    // 暴露到全局
    window.PerfMonitor = PerfMonitor;
    
    // 快捷键显示面板 (Ctrl+Shift+P)
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'P') {
            e.preventDefault();
            PerfMonitor.showPanel();
        }
    });
})();
