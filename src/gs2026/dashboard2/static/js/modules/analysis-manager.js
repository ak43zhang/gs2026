/**
 * AnalysisManager - 分析管理器
 * 管理所有AI分析模块和任务
 */
class AnalysisManager extends BaseManager {
    constructor() {
        super('analysis');
        this.modules = {};
        this.runningTasks = new Map();
        this.config = null;
    }

    async init() {
        await super.init();
        
        // 加载模块配置
        try {
            const response = await GS2026.api.get('/analysis/modules');
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
            deepseek: {
                name: 'DeepSeek AI分析',
                icon: '🤖',
                type: 'analysis',
                tasks: {
                    event_driven: { 
                        name: '领域事件分析', 
                        file: 'deepseek_analysis_event_driven.py',
                        params: []
                    },
                    news_cls: { 
                        name: '财联社数据分析', 
                        file: 'deepseek_analysis_news_cls.py',
                        params: []
                    },
                    news_combine: { 
                        name: '综合数据分析', 
                        file: 'deepseek_analysis_news_combine.py',
                        params: []
                    },
                    news_ztb: { 
                        name: '涨停板数据分析', 
                        file: 'deepseek_analysis_news_ztb.py',
                        params: []
                    },
                    notice: { 
                        name: '公告分析', 
                        file: 'deepseek_analysis_notice.py',
                        params: []
                    }
                }
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
    async getModuleTasks(moduleId) {
        try {
            const response = await GS2026.api.get(`/analysis/${moduleId}/tasks`);
            return response.data.tasks || [];
        } catch (e) {
            this.log('error', `Failed to load tasks for ${moduleId}`, { error: e.message });
            // 返回默认任务列表
            const module = this.modules[moduleId];
            if (module && module.tasks) {
                return Object.entries(module.tasks).map(([id, task]) => ({
                    id,
                    name: task.name,
                    params: task.params || []
                }));
            }
            return [];
        }
    }

    // 启动任务
    async startTask(moduleId, taskId, params = {}) {
        this.log('info', `Starting task: ${moduleId}/${taskId}`, params);
        
        try {
            const response = await GS2026.api.post(
                `/analysis/${moduleId}/start/${taskId}`,
                params
            );
            
            if (response.success) {
                this.log('info', `Task started: ${response.process_id}`);
                this.runningTasks.set(taskId, {
                    processId: response.process_id,
                    pid: response.pid,
                    startTime: new Date()
                });
                this.emit('taskStarted', { moduleId, taskId, processId: response.process_id });
                return { success: true, processId: response.process_id, pid: response.pid };
            } else {
                throw new Error(response.error || '启动失败');
            }
        } catch (e) {
            this.log('error', `Failed to start task: ${moduleId}/${taskId}`, { error: e.message });
            return { success: false, error: e.message };
        }
    }

    // 停止任务
    async stopTask(taskId) {
        const task = this.runningTasks.get(taskId);
        if (!task) {
            return { success: false, error: '任务未运行' };
        }

        this.log('info', `Stopping task: ${taskId}`);
        
        try {
            const response = await GS2026.api.post(`/analysis/stop/${task.processId}`);
            
            if (response.success) {
                this.log('info', `Task stopped: ${taskId}`);
                this.runningTasks.delete(taskId);
                this.emit('taskStopped', { taskId });
                return { success: true };
            } else {
                throw new Error(response.error || '停止失败');
            }
        } catch (e) {
            this.log('error', `Failed to stop task: ${taskId}`, { error: e.message });
            return { success: false, error: e.message };
        }
    }

    // 停止进程
    async stopProcess(processId) {
        this.log('info', `Stopping process: ${processId}`);
        
        try {
            const response = await GS2026.api.post(`/analysis/stop/${processId}`);
            
            if (response.success) {
                this.log('info', `Process stopped: ${processId}`);
                // 从运行列表中移除
                for (const [taskId, task] of this.runningTasks) {
                    if (task.processId === processId) {
                        this.runningTasks.delete(taskId);
                        break;
                    }
                }
                this.emit('processStopped', { processId });
                return { success: true };
            } else {
                throw new Error(response.error || '停止失败');
            }
        } catch (e) {
            this.log('error', `Failed to stop process: ${processId}`, { error: e.message });
            return { success: false, error: e.message };
        }
    }

    // 获取任务状态
    getTaskStatus(taskId) {
        return this.runningTasks.get(taskId);
    }

    // 检查任务是否运行中
    isTaskRunning(taskId) {
        return this.runningTasks.has(taskId);
    }

    // 获取所有运行中的任务
    getRunningTasks() {
        return Array.from(this.runningTasks.entries()).map(([taskId, info]) => ({
            taskId,
            ...info
        }));
    }

    // 获取进程列表
    async getProcessList() {
        try {
            const response = await GS2026.api.get('/analysis/status');
            return response.data.processes || [];
        } catch (e) {
            this.log('error', 'Failed to get process list', { error: e.message });
            return [];
        }
    }

    // 启动定时刷新
    startPolling() {
        // 每10秒刷新一次状态（减少刷新频率，避免干扰编辑）
        setInterval(async () => {
            await this.refreshStatus();
        }, 10000);
    }

    // 刷新状态
    async refreshStatus() {
        try {
            const processes = await this.getProcessList();
            
            // 更新运行任务列表
            this.runningTasks.clear();
            processes.forEach(proc => {
                if (proc.status === 'running') {
                    const taskId = proc.service_id ? proc.service_id.replace('analysis_', '') : '';
                    if (taskId) {
                        this.runningTasks.set(taskId, {
                            processId: proc.process_id,
                            pid: proc.pid,
                            startTime: proc.start_time
                        });
                    }
                }
            });
            
            this.emit('statusRefreshed', processes);
        } catch (e) {
            this.log('error', 'Failed to refresh status', { error: e.message });
        }
    }
}
