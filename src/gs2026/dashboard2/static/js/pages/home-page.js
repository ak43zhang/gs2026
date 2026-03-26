/**
 * HomePage - 首页控制器
 * 采用模块化架构，使用组件化设计
 */

class HomePage {
    constructor() {
        this.initialized = false;
        this.statusPolling = null;
        this.collectionManager = null;
    }

    async init() {
        if (this.initialized) return;

        // 初始化采集管理器（用于获取状态）
        if (typeof CollectionManager !== 'undefined') {
            this.collectionManager = new CollectionManager();
            await this.collectionManager.init();
        }

        // 绑定事件
        this.bindEvents();

        // 加载初始数据
        await this.loadSystemStatus();

        // 启动定时刷新
        this.startPolling();

        this.initialized = true;
        GS2026.logger?.info('HomePage initialized');
    }

    bindEvents() {
        // 卡片点击事件（事件委托）
        document.addEventListener('click', (e) => {
            const card = e.target.closest('.card');
            if (card) {
                const href = card.dataset.href;
                if (href) {
                    window.location.href = href;
                }
            }
        });
    }

    async loadSystemStatus() {
        try {
            // 并行加载所有状态
            const [processData, healthData] = await Promise.all([
                this.fetchProcessData(),
                this.fetchHealthData()
            ]);

            this.updateStatusCards({
                processes: processData,
                redis: healthData?.redis || { ok: false },
                database: healthData?.database || { ok: false },
                lastUpdate: new Date()
            });
        } catch (e) {
            GS2026.logger?.error('Failed to load system status', { error: e.message });
        }
    }

    async fetchProcessData() {
        try {
            const response = await GS2026.api.get('/collection/control/status');
            if (response.success) {
                const data = response.data;
                const runningCount = data ? (
                    (data.collection?.running ? 1 : 0) +
                    (data.analysis?.running ? 1 : 0) +
                    (data.monitor?.running ? 1 : 0)
                ) : 0;
                
                return {
                    count: runningCount,
                    details: data,
                    ok: true
                };
            }
            return { count: 0, details: {}, ok: false };
        } catch (e) {
            GS2026.logger?.warn('Failed to fetch process data', { error: e.message });
            return { count: 0, details: {}, ok: false };
        }
    }

    async fetchHealthData() {
        try {
            const response = await GS2026.api.get('/collection/health');
            if (response.success) {
                return response.data;
            }
            return { redis: { ok: false }, database: { ok: false } };
        } catch (e) {
            GS2026.logger?.warn('Failed to fetch health data', { error: e.message });
            return { redis: { ok: false }, database: { ok: false } };
        }
    }

    async checkRedis() {
        // 使用 health 接口
        const health = await this.fetchHealthData();
        return health.redis || { ok: false };
    }

    async checkDatabase() {
        // 使用 health 接口
        const health = await this.fetchHealthData();
        return health.database || { ok: false };
    }

    updateStatusCards(data) {
        // 更新进程数
        const processEl = document.getElementById('total-processes');
        if (processEl) {
            processEl.textContent = data.processes?.count ?? '-';
            
            // 根据进程数设置颜色
            if (data.processes?.count > 0) {
                processEl.style.color = '#52c41a'; // 绿色
            } else if (data.processes?.ok === false) {
                processEl.style.color = '#f5222d'; // 红色
            } else {
                processEl.style.color = '#8c8c8c'; // 灰色
            }
        }

        // 更新 Redis 状态
        const redisEl = document.getElementById('redis-status');
        if (redisEl) {
            if (data.redis?.ok) {
                redisEl.textContent = '🟢';
                redisEl.title = 'Redis 连接正常';
                redisEl.style.color = '#52c41a';
            } else {
                redisEl.textContent = '🔴';
                redisEl.title = 'Redis 连接失败';
                redisEl.style.color = '#f5222d';
            }
        }

        // 更新数据库状态
        const dbEl = document.getElementById('db-status');
        if (dbEl) {
            if (data.database?.ok) {
                dbEl.textContent = '🟢';
                dbEl.title = '数据库连接正常';
                dbEl.style.color = '#52c41a';
            } else {
                dbEl.textContent = '🔴';
                dbEl.title = '数据库连接失败';
                dbEl.style.color = '#f5222d';
            }
        }

        // 更新时间
        const timeEl = document.getElementById('last-update');
        if (timeEl && data.lastUpdate) {
            timeEl.textContent = data.lastUpdate.toLocaleTimeString('zh-CN');
        }
    }

    startPolling(interval = 10000) {
        if (this.statusPolling) {
            clearInterval(this.statusPolling);
        }

        this.statusPolling = setInterval(() => {
            this.refreshStatus();
        }, interval);
    }

    stopPolling() {
        if (this.statusPolling) {
            clearInterval(this.statusPolling);
            this.statusPolling = null;
        }
    }

    async refreshStatus() {
        await this.loadSystemStatus();
    }

    destroy() {
        this.stopPolling();
        if (this.collectionManager) {
            this.collectionManager.destroy();
        }
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', async () => {
    const page = new HomePage();
    await page.init();
});
