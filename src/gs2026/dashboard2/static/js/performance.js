/**
 * 性能监控页面 - Performance Monitor
 * 功能：API性能监控、数据库分析、前端性能监控
 */

class PerformanceMonitor {
    constructor() {
        this.autoRefresh = true;
        this.refreshInterval = 5000; // 5秒
        this.timer = null;
        this.frontendMetrics = [];
        this.isLoading = false;

        this.init();
    }

    init() {
        this.bindEvents();
        this.startAutoRefresh();
        this.loadAllData();
        this.initFrontendMonitor();
        console.log('[PerformanceMonitor] 初始化完成');
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
        const autoRefreshCheckbox = document.getElementById('auto-refresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.addEventListener('change', (e) => {
                this.autoRefresh = e.target.checked;
                if (this.autoRefresh) {
                    this.startAutoRefresh();
                    console.log('[PerformanceMonitor] 自动刷新已开启');
                } else {
                    this.stopAutoRefresh();
                    console.log('[PerformanceMonitor] 自动刷新已关闭');
                }
            });
        }
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

        console.log(`[PerformanceMonitor] 切换到Tab: ${tab}`);
    }

    startAutoRefresh() {
        if (this.timer) return;
        this.timer = setInterval(() => this.loadAllData(), this.refreshInterval);
        console.log('[PerformanceMonitor] 自动刷新已启动 (5s)');
    }

    stopAutoRefresh() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
            console.log('[PerformanceMonitor] 自动刷新已停止');
        }
    }

    async loadAllData() {
        if (this.isLoading) return;
        this.isLoading = true;

        try {
            await Promise.all([
                this.loadApiData(),
                this.loadDbData(),
                this.loadHistoryStats()
            ]);
            this.updateFrontendCard();
        } catch (error) {
            console.error('[PerformanceMonitor] 加载数据失败:', error);
        } finally {
            this.isLoading = false;
        }
    }

    async loadHistoryStats() {
        try {
            const response = await fetch('/api/performance/slow-stats');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const result = await response.json();

            if (!result.success) {
                console.warn('[PerformanceMonitor] 历史统计数据加载失败:', result.error);
                return;
            }

            const stats = result.stats;

            // 更新历史统计卡片
            this.updateElement('history-slow-req', stats.slow_requests.total);
            this.updateElement('history-slow-req-avg', `平均: ${stats.slow_requests.avg_duration}ms`);

            this.updateElement('history-slow-query', stats.slow_queries.total);
            this.updateElement('history-slow-query-avg', `平均: ${stats.slow_queries.avg_duration}ms`);

            this.updateElement('history-slow-fe', stats.slow_frontend.total);
            this.updateElement('history-slow-fe-avg', `平均: ${stats.slow_frontend.avg_duration}ms`);

            // 更新时间
            const now = new Date();
            this.updateElement('history-refresh-time', `更新于 ${now.toLocaleTimeString('zh-CN')}`);

            // 更新前端慢资源数
            this.updateElement('fe-slow', stats.slow_frontend.total);

        } catch (error) {
            console.error('[PerformanceMonitor] 加载历史统计数据失败:', error);
        }
    }

    async loadApiData() {
        try {
            const response = await fetch('/diag/performance');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            const statusBadge = document.getElementById('api-status');
            if (!data.enabled) {
                if (statusBadge) {
                    statusBadge.textContent = '已禁用';
                    statusBadge.classList.add('disabled');
                }
                this.updateApiTable([]);
                return;
            }

            // 更新卡片数据
            this.updateElement('api-total', data.total_requests || 0);
            this.updateElement('api-avg', (data.duration?.avg || 0) + 'ms');
            this.updateElement('api-p95', (data.duration?.p95 || 0) + 'ms');

            // 计算慢请求数（>500ms）
            const slowCount = data.slow_requests?.length || 0;
            this.updateElement('api-slow', slowCount);

            // 更新表格
            this.updateApiTable(data.slow_requests || []);

        } catch (error) {
            console.error('[PerformanceMonitor] 加载API性能数据失败:', error);
            this.updateElement('api-status', '错误');
            document.getElementById('api-status')?.classList.add('disabled');
        }
    }

    async loadDbData() {
        try {
            const response = await fetch('/diag/db');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            const statusBadge = document.getElementById('db-status');
            if (!data.enabled) {
                if (statusBadge) {
                    statusBadge.textContent = '已禁用';
                    statusBadge.classList.add('disabled');
                }
                this.updateDbTable([]);
                return;
            }

            // 更新卡片数据
            this.updateElement('db-total', data.total_queries || 0);
            this.updateElement('db-avg', (data.duration?.avg || 0) + 'ms');
            this.updateElement('db-max', (data.duration?.max || 0) + 'ms');

            // 计算慢查询数
            const slowCount = data.recent_slow_queries?.length || 0;
            this.updateElement('db-slow', slowCount);

            // 更新表格
            this.updateDbTable(data.recent_slow_queries || []);

        } catch (error) {
            console.error('[PerformanceMonitor] 加载数据库数据失败:', error);
            this.updateElement('db-status', '错误');
            document.getElementById('db-status')?.classList.add('disabled');
        }
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    updateApiTable(requests) {
        const tbody = document.getElementById('api-table-body');
        if (!tbody) return;

        if (!requests || requests.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="7" class="empty-message">暂无数据</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = requests.slice(0, 20).map(req => `
            <tr>
                <td>${this.formatTime(req.timestamp)}</td>
                <td><span class="method-badge method-${req.method?.toLowerCase()}">${req.method}</span></td>
                <td title="${req.path}">${this.truncate(req.path, 40)}</td>
                <td><span class="status-badge-http status-${Math.floor(req.status_code / 100)}xx">${req.status_code}</span></td>
                <td class="${this.getDurationClass(req.duration_ms)}">${req.duration_ms}ms</td>
                <td>${req.db_queries || 0}</td>
                <td>${req.redis_queries || 0}</td>
            </tr>
        `).join('');
    }

    updateDbTable(queries) {
        const tbody = document.getElementById('db-table-body');
        if (!tbody) return;

        if (!queries || queries.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="3" class="empty-message">暂无数据</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = queries.slice(0, 20).map(q => `
            <tr>
                <td>${this.formatTime(q.timestamp)}</td>
                <td class="sql-cell" title="${this.escapeHtml(q.statement)}">
                    <div class="sql-content">${this.escapeHtml(q.statement)}</div>
                </td>
                <td class="${this.getDurationClass(q.duration_ms)}">${q.duration_ms}ms</td>
            </tr>
        `).join('');
    }

    getDurationClass(ms) {
        if (ms === undefined || ms === null) return '';
        if (ms < 100) return 'duration-good';
        if (ms < 500) return 'duration-warning';
        return 'duration-bad';
    }

    formatTime(timestamp) {
        if (!timestamp) return '-';
        try {
            const date = new Date(timestamp);
            return date.toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (e) {
            return timestamp;
        }
    }

    truncate(str, maxLength) {
        if (!str) return '-';
        if (str.length <= maxLength) return str;
        return str.substring(0, maxLength) + '...';
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 前端性能监控
    initFrontendMonitor() {
        // 拦截XHR请求
        const originalXHR = window.XMLHttpRequest;
        const self = this;

        window.XMLHttpRequest = function() {
            const xhr = new originalXHR();
            const startTime = performance.now();
            let requestUrl = '';

            const originalOpen = xhr.open;
            xhr.open = function(method, url) {
                requestUrl = url;
                return originalOpen.apply(this, arguments);
            };

            xhr.addEventListener('loadend', function() {
                const duration = Math.round(performance.now() - startTime);
                const metric = {
                    type: 'xhr',
                    url: requestUrl || xhr.responseURL,
                    duration: duration,
                    timestamp: new Date().toISOString()
                };

                self.frontendMetrics.push(metric);

                // 只保留最近100条
                if (self.frontendMetrics.length > 100) {
                    self.frontendMetrics.shift();
                }

                self.updateFrontendCard();
                self.updateFrontendTable();

                // 上报慢资源（>1000ms）
                if (duration > 1000) {
                    self.reportSlowFrontend({
                        resource_type: 'xhr',
                        url: metric.url,
                        duration_ms: duration,
                        page_url: window.location.href,
                        extra_info: {
                            status: xhr.status,
                            statusText: xhr.statusText
                        }
                    });
                }
            });

            return xhr;
        };

        // 拦截Fetch请求
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const startTime = performance.now();
            const url = args[0];

            return originalFetch.apply(this, args).then(response => {
                const duration = Math.round(performance.now() - startTime);
                const metric = {
                    type: 'fetch',
                    url: typeof url === 'string' ? url : url.url,
                    duration: duration,
                    timestamp: new Date().toISOString()
                };

                self.frontendMetrics.push(metric);

                if (self.frontendMetrics.length > 100) {
                    self.frontendMetrics.shift();
                }

                self.updateFrontendCard();
                self.updateFrontendTable();

                // 上报慢资源（>1000ms）
                if (duration > 1000) {
                    self.reportSlowFrontend({
                        resource_type: 'fetch',
                        url: metric.url,
                        duration_ms: duration,
                        page_url: window.location.href,
                        extra_info: {
                            status: response.status,
                            statusText: response.statusText
                        }
                    });
                }

                return response;
            });
        };

        console.log('[PerformanceMonitor] 前端性能监控已启动');
    }

    // 上报慢资源到后端
    async reportSlowFrontend(data) {
        try {
            await fetch('/api/performance/slow-frontend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data),
                keepalive: true
            });
        } catch (e) {
            // 上报失败不影响前端
            console.debug('[PerformanceMonitor] 慢资源上报失败:', e);
        }
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

        this.updateElement('fe-total', total);
        this.updateElement('fe-avg', avg + 'ms');
        this.updateElement('fe-max', max + 'ms');
        this.updateElement('fe-xhr', xhrCount);
    }

    updateFrontendTable() {
        const tbody = document.getElementById('fe-table-body');
        if (!tbody) return;

        if (this.frontendMetrics.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="4" class="empty-message">暂无数据</td>
                </tr>
            `;
            return;
        }

        const metrics = [...this.frontendMetrics].reverse().slice(0, 20);

        tbody.innerHTML = metrics.map(m => `
            <tr>
                <td><span class="type-badge type-${m.type}">${m.type.toUpperCase()}</span></td>
                <td title="${m.url}">${this.truncate(m.url, 50)}</td>
                <td class="${this.getDurationClass(m.duration)}">${m.duration}ms</td>
                <td>-</td>
            </tr>
        `).join('');
    }
}

// 全局刷新函数
function refreshAll() {
    if (window.performanceMonitor) {
        window.performanceMonitor.loadAllData();
        console.log('[PerformanceMonitor] 手动刷新完成');
    }
}

// 全局重置函数
async function resetAll() {
    if (!confirm('确定要重置所有性能统计吗？此操作不可恢复。')) return;

    try {
        // 重置API统计
        const apiResponse = await fetch('/diag/performance/reset', { method: 'POST' });
        if (!apiResponse.ok) {
            console.warn('[PerformanceMonitor] API统计重置失败');
        }

        // 重置数据库统计
        const dbResponse = await fetch('/diag/db/reset', { method: 'POST' });
        if (!dbResponse.ok) {
            console.warn('[PerformanceMonitor] 数据库统计重置失败');
        }

        // 重置前端统计
        if (window.performanceMonitor) {
            window.performanceMonitor.frontendMetrics = [];
            window.performanceMonitor.updateFrontendCard();
            window.performanceMonitor.updateFrontendTable();
        }

        // 刷新数据
        refreshAll();

        console.log('[PerformanceMonitor] 所有统计已重置');
        alert('统计已重置');

    } catch (error) {
        console.error('[PerformanceMonitor] 重置统计失败:', error);
        alert('重置失败: ' + error.message);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    window.performanceMonitor = new PerformanceMonitor();
});

// 页面卸载时清理
document.addEventListener('beforeunload', () => {
    if (window.performanceMonitor) {
        window.performanceMonitor.stopAutoRefresh();
    }
});
