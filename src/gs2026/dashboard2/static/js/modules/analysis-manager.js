/**
 * AnalysisManager - 分析管理器
 * 管理所有AI分析模块和任务（支持多开）
 * 采用与 CollectionManager 相同的模式
 */
class AnalysisManager extends BaseManager {
    constructor() {
        super('analysis');
        this.modules = {};
        this.runningTasks = new Map();  // key: process_id, value: task info
        this.config = null;
        this.pollingInterval = null;
    }

    async init() {
        await super.init();
        
        // 强制从后端加载配置（不使用默认配置）
        try {
            // 添加时间戳防止缓存
            const timestamp = Date.now();
            const response = await GS2026.api.get(`/analysis/modules?t=${timestamp}`);
            
            if (response.data && response.data.modules) {
                this.config = response.data;
                this.modules = this.config.modules || {};
                this.log('info', `Loaded ${Object.keys(this.modules).length} modules from server`);
                this.emit('modulesLoaded', this.modules);
            } else {
                throw new Error('Invalid response format');
            }
        } catch (e) {
            this.log('error', 'Failed to load modules from server', { error: e.message });
            // 不加载默认配置，而是显示错误
            this.modules = {};
            this.emit('error', { message: '无法加载模块配置，请刷新页面重试' });
        }

        // 启动定时刷新
        this.startPolling();
    }

    // 获取模块列表
    getModules() {
        return this.modules;
    }

    // 获取单个模块
    getModule(moduleId) {
        return this.modules[moduleId];
    }

    // 获取模块任务
    getModuleTasks(moduleId) {
        const module = this.modules[moduleId];
        return module ? module.tasks : {};
    }

    // 启动任务
    async startTask(moduleId, taskId, params = {}) {
        this.log('info', `Starting ${moduleId}/${taskId}`, params);

        try {
            const result = await GS2026.api.post(`/analysis/${moduleId}/start/${taskId}`, params);
            
            if (result.success) {
                this.emit('taskStarted', { moduleId, taskId, processId: result.process_id, pid: result.pid });
                this.log('success', `Started ${taskId}`, { pid: result.pid, processId: result.process_id });
                // 立即刷新状态
                await this.refreshStatus();
            } else {
                this.log('error', `Failed to start ${taskId}`, { error: result.message });
            }

            return result;
        } catch (e) {
            this.log('error', `Failed to start ${taskId}`, { error: e.message });
            throw e;
        }
    }

    // 停止任务（采用 CollectionManager 模式）
    async stopTask(processId) {
        this.log('info', `Stopping ${processId}`);
        console.log(`[DEBUG] AnalysisManager.stopTask called: ${processId}`);

        try {
            const result = await GS2026.api.post(`/analysis/stop/${processId}`);
            console.log(`[DEBUG] API result:`, result);
            
            // 将后端的 message 映射为 error，与前端兼容
            if (!result.success && result.message && !result.error) {
                result.error = result.message;
            }
            
            if (result.success) {
                this.runningTasks.delete(processId);
                this.emit('taskStopped', { processId });
                this.log('success', `Stopped ${processId}`);
            } else {
                // 如果后端返回未在运行，也从前端移除（进程已消失）
                if (result.message && (result.message.includes('未在运行') || result.message.includes('不存在'))) {
                    this.log('info', `Process ${processId} not found on server, removing from local`);
                    this.runningTasks.delete(processId);
                    this.emit('taskStopped', { processId });
                }
            }

            return result;
        } catch (e) {
            this.log('error', `Failed to stop ${processId}`, { error: e.message });
            console.error(`[DEBUG] API error:`, e);
            // 返回对象而不是抛出异常，与 analysis-page.js 兼容
            return { success: false, error: e.message };
        }
    }

    // 停止全部任务
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

    // 刷新状态（采用 CollectionManager 模式：清空重新填充）
    async refreshStatus() {
        try {
            const result = await GS2026.api.get('/analysis/status');
            
            // 清空并重新填充（与 CollectionManager 一致）
            this.runningTasks.clear();
            
            if (result.data && result.data.processes) {
                result.data.processes.forEach(proc => {
                    if (proc.status === 'running') {
                        // 判断任务类型
                        const serviceId = proc.service_id || '';
                        let moduleId = 'unknown';
                        let taskId = serviceId;
                        
                        if (serviceId.startsWith('analysis_')) {
                            moduleId = 'deepseek';
                            taskId = serviceId.replace('analysis_', '');
                        }
                        
                        this.runningTasks.set(proc.process_id, {
                            processId: proc.process_id,
                            serviceId: serviceId,
                            moduleId: moduleId,
                            taskId: taskId,
                            pid: proc.pid,
                            status: proc.status,
                            startTime: new Date(proc.start_time).getTime(),
                            params: proc.params || {}
                        });
                    }
                });
            }

            this.emit('statusRefreshed', this.getRunningTasks());
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

    // 获取特定任务的运行实例
    getTaskInstances(moduleId, taskId) {
        return this.getRunningTasks().filter(task => 
            task.moduleId === moduleId && task.taskId === taskId
        );
    }

    // 启动定时刷新
    startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        // 每10秒刷新一次
        this.pollingInterval = setInterval(() => {
            this.refreshStatus();
        }, 10000);
        
        // 立即刷新一次
        this.refreshStatus();
    }

    // 停止定时刷新
    stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    // 销毁
    destroy() {
        this.stopPolling();
        super.destroy();
    }
}

// 导出
window.AnalysisManager = AnalysisManager;
