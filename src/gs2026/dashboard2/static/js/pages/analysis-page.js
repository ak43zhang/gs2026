/**
 * AnalysisPage - 分析页面
 * 主页面控制器（支持多开分析服务）
 */
class AnalysisPage {
    constructor() {
        this.analysisManager = null;
        this.components = {};
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;

        console.log('[AnalysisPage] Initializing...');

        // 初始化管理器
        this.analysisManager = new AnalysisManager();
        await this.analysisManager.init();

        // 初始化组件
        this.initComponents();

        // 绑定事件
        this.bindEvents();

        // 初始渲染
        this.render();

        this.initialized = true;
        console.log('[AnalysisPage] Initialized');
    }

    initComponents() {
        // Tab导航
        const modules = this.analysisManager.getModules();
        
        const tabs = Object.entries(modules).map(([id, mod]) => ({
            id,
            name: mod.name,
            icon: mod.icon
        }));

        this.components.tabNav = new TabNav('tab-nav', {
            tabs,
            defaultTab: 'deepseek',
            on: {
                switch: (tabId) => this.switchModule(tabId)
            }
        });

        // 服务网格容器
        this.components.serviceGrid = {
            container: document.getElementById('service-grid'),
            cards: new Map(),

            render: (moduleId, tasksData) => {
                console.log('[AnalysisPage] Rendering tasks:', tasksData);
                if (!this.components.serviceGrid.container) return;

                // 清空旧卡片
                this.components.serviceGrid.container.innerHTML = '';
                this.components.serviceGrid.cards.clear();

                // 创建新卡片
                tasksData.forEach((task, index) => {
                    console.log(`[AnalysisPage] Creating card ${index}:`, task);
                    
                    const cardContainer = document.createElement('div');
                    cardContainer.id = `task-card-${task.id}`;
                    this.components.serviceGrid.container.appendChild(cardContainer);
                    
                    const card = new ServiceCard(cardContainer.id, {
                        taskId: task.id,
                        moduleId: moduleId,
                        config: {
                            name: task.name,
                            params: task.params || []
                        },
                        status: { running: false },
                        on: {
                            start: ({ taskId, params }) => this.startTask(taskId, params)
                        }
                    });

                    card.render();
                    this.components.serviceGrid.cards.set(task.id, card);
                });

                this.updateTaskStatuses();
            },

            updateStatus: () => {
                this.components.serviceGrid.cards.forEach((card, taskId) => {
                    // 获取该任务的所有运行实例
                    const instances = this.analysisManager.getTaskInstances('deepseek', taskId);
                    const isRunning = instances.length > 0;
                    
                    card.updateStatus({ 
                        status: isRunning ? 'running' : 'stopped',
                        instanceCount: instances.length,
                        instances: instances
                    });
                });
            }
        };

        // 进程列表组件（类似数据采集页面）
        this.components.processList = new ProcessList('process-list', {
            on: {
                stop: ({ processId }) => this.stopProcess(processId),
                stopAll: () => this.stopAllProcesses()
            }
        });
    }

    bindEvents() {
        // 监听管理器事件
        this.analysisManager.on('taskStarted', () => {
            this.updateTaskStatuses();
            this.refreshProcessList();
        });

        this.analysisManager.on('taskStopped', () => {
            this.updateTaskStatuses();
            this.refreshProcessList();
        });

        this.analysisManager.on('statusRefreshed', () => {
            this.updateTaskStatuses();
            this.refreshProcessList();
        });
    }

    render() {
        this.switchModule('deepseek');
        this.refreshProcessList();
    }

    async switchModule(moduleId) {
        console.log(`[AnalysisPage] Switching to module: ${moduleId}`);
        
        const module = this.analysisManager.getModule(moduleId);
        if (!module) return;

        const tasks = Object.entries(module.tasks).map(([id, task]) => ({
            id,
            ...task
        }));
        
        this.components.serviceGrid.render(moduleId, tasks);
    }

    async startTask(taskId, params) {
        console.log(`[AnalysisPage] Starting task: ${taskId}`, params);
        
        const result = await this.analysisManager.startTask(
            'deepseek',
            taskId,
            params
        );
        
        if (result.success) {
            console.log(`[AnalysisPage] Task started: ${result.processId}`);
            this.refreshProcessList();
        } else {
            console.error(`[AnalysisPage] Failed to start task: ${result.error}`);
            alert(`启动失败: ${result.error}`);
        }
    }

    async stopTask(taskId) {
        console.log(`[AnalysisPage] Stopping task: ${taskId}`);
        
        // 获取该任务的运行实例
        const instances = this.analysisManager.getTaskInstances('deepseek', taskId);
        
        if (instances.length === 0) {
            alert('任务未运行');
            return;
        }
        
        // 停止最新的实例
        const latestInstance = instances[instances.length - 1];
        const result = await this.analysisManager.stopTask(latestInstance.processId);
        
        if (result.success) {
            console.log(`[AnalysisPage] Task stopped: ${latestInstance.processId}`);
            this.updateTaskStatuses();
            this.refreshProcessList();
        } else {
            console.error(`[AnalysisPage] Failed to stop task: ${result.error}`);
            alert(`停止失败: ${result.error}`);
        }
    }

    async stopProcess(processId) {
        console.log(`[AnalysisPage] Stopping process: ${processId}`);
        
        const result = await this.analysisManager.stopTask(processId);
        
        if (result.success) {
            console.log(`[AnalysisPage] Process stopped: ${processId}`);
            this.updateTaskStatuses();
            this.refreshProcessList();
        } else {
            console.error(`[AnalysisPage] Failed to stop process: ${result.error}`);
            alert(`停止失败: ${result.error}`);
        }
    }

    async stopAllProcesses() {
        console.log('[AnalysisPage] Stopping all processes');
        
        const tasks = this.analysisManager.getRunningTasks();
        const results = await Promise.all(
            tasks.map(task => this.analysisManager.stopTask(task.processId))
        );
        
        const successCount = results.filter(r => r.success).length;
        console.log(`[AnalysisPage] Stopped ${successCount}/${tasks.length} processes`);
        
        this.updateTaskStatuses();
        this.refreshProcessList();
    }

    updateTaskStatuses() {
        if (this.components.serviceGrid) {
            this.components.serviceGrid.updateStatus();
        }
    }

    // 刷新进程列表（使用 ProcessList 组件）
    refreshProcessList() {
        const tasks = this.analysisManager.getRunningTasks();
        
        // 转换为 ProcessList 需要的格式
        const processes = tasks.map(task => ({
            process_id: task.processId,
            module: 'analysis',
            taskId: task.taskId,
            service_id: task.serviceId,
            pid: task.pid,
            status: task.status,
            startTime: task.startTime
        }));
        
        if (this.components.processList) {
            this.components.processList.update(processes);
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.analysisPage = new AnalysisPage();
    window.analysisPage.init();
});
