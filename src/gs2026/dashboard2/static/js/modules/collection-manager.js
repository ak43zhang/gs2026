/**
 * CollectionManager - 采集管理器
 * 管理所有采集模块和任务
 */

class CollectionManager extends BaseManager {
    constructor() {
        super('collection');
        this.modules = {};
        this.runningTasks = new Map();
        this.config = null;
    }

    async init() {
        await super.init();
        
        // 加载模块配置
        try {
            const response = await GS2026.api.get('/collection/modules');
            this.config = response.data;
            this.modules = this.config.modules || {};
            this.log('info', `Loaded ${Object.keys(this.modules).length} modules`);
            this.emit('modulesLoaded', this.modules);
        } catch (e) {
            this.log('error', 'Failed to load modules', { error: e.message });
            // 使用默认配置
            this.loadDefaultConfig();
        }

        // 启动定时刷新
        this.startPolling();
    }

    // 加载默认配置
    loadDefaultConfig() {
        this.modules = {
            monitor: {
                name: '开市采集',
                icon: '👁️',
                type: 'monitor',
                tasks: {
                    stock: { name: '股票监控', file: 'monitor_stock.py' },
                    bond: { name: '债券监控', file: 'monitor_bond.py' },
                    industry: { name: '行业监控', file: 'monitor_industry.py' },
                    dp_signal: { name: '大盘信号', file: 'monitor_dp_signal.py' },
                    gp_zq_signal: { name: '股债联动', file: 'monitor_gp_zq_rising_signal.py' }
                }
            },
            base: {
                name: '基础采集',
                icon: '📊',
                type: 'collection',
                tasks: {
                    wencai_base: { name: '问财基础数据', file: 'wencai_collection.py', function: 'collect_base_query' },
                    wencai_hot: { name: '问财热股数据', file: 'wencai_collection.py', function: 'collect_popularity_query' },
                    ztb: { name: '涨停板数据', file: 'zt_collection.py', function: 'collect_ztb_query' },
                    zt_zb: { name: '涨停炸板数据', file: 'zt_collection.py', function: 'collect_zt_zb_collection' },
                    zskj: { name: '知识库数据', file: 'base_collection.py', function: 'zskj' },
                    today_lhb: { name: '今日龙虎榜', file: 'base_collection.py', function: 'today_lhb' },
                    rzrq: { name: '融资融券', file: 'base_collection.py', function: 'rzrq' },
                    gsdt: { name: '公司动态', file: 'base_collection.py', function: 'gsdt' },
                    history_lhb: { name: '历史龙虎榜', file: 'base_collection.py', function: 'history_lhb' },
                    risk_tdx: { name: '通达信风险', file: 'base_collection.py', function: 'risk_tdx' },
                    industry_ths: { name: '同花顺行业', file: 'base_collection.py', function: 'industry_ths' },
                    industry_code_component_ths: { name: '同花顺行业成分', file: 'base_collection.py', function: 'industry_code_component_ths' }
                }
            },
            news: {
                name: '消息采集',
                icon: '📰',
                type: 'collection',
                tasks: {}
            },
            risk: {
                name: '风险采集',
                icon: '⚠️',
                type: 'collection',
                tasks: {}
            }
        };
    }

    // 获取模块列表
    getModules() {
        return this.modules;
    }

    // 获取模块
    getModule(moduleId) {
        return this.modules[moduleId];
    }

    // 获取模块任务
    getModuleTasks(moduleId) {
        const tasks = this.modules[moduleId]?.tasks || {};
        // 转换为列表，保持顺序
        return Object.entries(tasks).map(([id, config]) => ({ id, ...config }));
    }

    // 获取任务配置
    getTaskConfig(moduleId, taskId) {
        return this.modules[moduleId]?.tasks?.[taskId];
    }

    // 启动任务
    async startTask(moduleId, taskId, params = {}) {
        this.log('info', `Starting ${moduleId}.${taskId}`, params);

        try {
            const result = await GS2026.api.post(
                `/collection/${moduleId}/start/${taskId}`,
                params
            );

            if (result.success) {
                // 根据模块类型设置不同的状态
                const module = this.modules[moduleId];
                const isMonitor = module && module.type === 'monitor';
                
                if (isMonitor) {
                    // 监控类任务 - 持续运行
                    this.runningTasks.set(result.process_id, {
                        moduleId,
                        taskId,
                        processId: result.process_id,
                        pid: result.pid,
                        startTime: Date.now(),
                        status: 'running',
                        taskType: 'monitor'
                    });
                } else {
                    // 采集类任务 - 批量执行，显示"执行中"30秒后自动完成
                    this.runningTasks.set(result.process_id, {
                        moduleId,
                        taskId,
                        processId: result.process_id,
                        pid: result.pid,
                        startTime: Date.now(),
                        status: 'executing',  // 执行中
                        taskType: 'collection'
                    });
                    
                    // 30秒后自动标记为完成
                    setTimeout(() => {
                        const task = this.runningTasks.get(result.process_id);
                        if (task && task.status === 'executing') {
                            task.status = 'completed';
                            this.emit('taskCompleted', { processId: result.process_id });
                            this.log('info', `Task ${taskId} completed`);
                        }
                    }, 30000);  // 30秒
                }
                
                this.emit('taskStarted', result);
                this.log('success', `Started ${taskId}`, { pid: result.pid });
            }

            return result;
        } catch (e) {
            this.log('error', `Failed to start ${taskId}`, { error: e.message });
            throw e;
        }
    }

    // 停止任务
    async stopTask(processId) {
        console.log('[DEBUG] CollectionManager.stopTask called:', processId);
        this.log('info', `Stopping ${processId}`);

        try {
            const result = await GS2026.api.post(`/collection/stop/${processId}`);
            console.log('[DEBUG] API result:', result);

            if (result.success) {
                this.runningTasks.delete(processId);
                this.emit('taskStopped', { processId });
                this.log('success', `Stopped ${processId}`);
            }

            return result;
        } catch (e) {
            console.error('[DEBUG] API error:', e);
            this.log('error', `Failed to stop ${processId}`, { error: e.message });
            throw e;
        }
    }

    // 停止全部任务（方案A实现）
    async stopAll() {
        this.log('warn', 'Stopping all tasks...');

        // 获取所有运行中的进程
        const processes = Array.from(this.runningTasks.keys());
        
        if (processes.length === 0) {
            this.log('info', 'No running tasks');
            return { success: true, stopped: 0 };
        }

        let stopped = 0;
        for (const processId of processes) {
            try {
                await this.stopTask(processId);
                stopped++;
                await GS2026.utils.sleep(500);
            } catch (e) {
                this.log('error', `Failed to stop ${processId}`, { error: e.message });
            }
        }

        this.emit('allStopped', { stopped });
        this.log('success', `Stopped ${stopped} tasks`);
        return { success: true, stopped };
    }

    // 刷新状态
    async refreshStatus() {
        try {
            const result = await GS2026.api.get('/collection/status');
            
            // 调试：输出第一个进程数据
            if (result.data && result.data.length > 0) {
                console.log('[DEBUG] CollectionManager first process:', result.data[0]);
            }
            
            // 更新运行任务列表
            this.runningTasks.clear();
            if (result.data) {
                result.data.forEach(proc => {
                    if (proc.status === 'running') {
                        this.runningTasks.set(proc.process_id, proc);
                    }
                });
            }

            this.emit('statusRefreshed', Array.from(this.runningTasks.values()));
            return result;
        } catch (e) {
            this.log('error', 'Failed to refresh status', { error: e.message });
            throw e;
        }
    }

    // 获取运行中的任务
    getRunningTasks() {
        return Array.from(this.runningTasks.values());
    }

    // 获取任务状态
    getTaskStatus(processId) {
        return this.runningTasks.get(processId);
    }

    // 启动定时刷新
    startPolling(interval = 10000) {
        // 清除旧的定时器
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
        }

        // 立即刷新一次
        this.refreshStatus();

        // 定时刷新
        this.pollingTimer = setInterval(() => {
            this.refreshStatus();
        }, interval);

        this.log('info', `Started polling every ${interval}ms`);
    }

    // 停止定时刷新
    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    }

    // 销毁
    async destroy() {
        this.stopPolling();
        await super.destroy();
    }
}
