/**
 * AnalysisPage - 分析页面
 * 主页面控制器
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
        
        // 构建 tabs 数组
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

        // 进程列表
        this.components.processList = new ProcessList('process-list', {
            on: {
                stop: ({ processId }) => this.stopProcess(processId)
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
                    
                    // 为每个卡片创建独立的容器
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
                            start: ({ taskId, params }) => this.startTask(taskId, params),
                            stop: ({ taskId }) => this.stopTask(taskId)
                        }
                    });

                    card.render();
                    this.components.serviceGrid.cards.set(task.id, card);
                });

                // 更新状态
                this.updateTaskStatuses();
            },

            updateStatus: () => {
                this.components.serviceGrid.cards.forEach((card, taskId) => {
                    const isRunning = this.analysisManager.isTaskRunning(taskId);
                    const status = this.analysisManager.getTaskStatus(taskId);
                    card.updateStatus({ 
                        status: isRunning ? 'running' : 'stopped',
                        pid: status?.pid 
                    });
                });
            }
        };
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
        // 渲染初始模块
        this.switchModule('deepseek');
    }

    async switchModule(moduleId) {
        console.log(`[AnalysisPage] Switching to module: ${moduleId}`);
        
        // 加载任务
        const tasks = await this.analysisManager.getModuleTasks(moduleId);
        console.log(`[AnalysisPage] Loaded ${tasks.length} tasks:`, tasks);
        
        // 渲染任务卡片
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
            
            // 更新卡片状态
            const card = this.components.serviceGrid.cards.get(taskId);
            if (card) {
                card.updateStatus({ status: 'running', pid: result.pid });
            }
        } else {
            console.error(`[AnalysisPage] Failed to start task: ${result.error}`);
            alert(`启动失败: ${result.error}`);
        }
    }

    async stopTask(taskId) {
        console.log(`[AnalysisPage] Stopping task: ${taskId}`);
        
        const result = await this.analysisManager.stopTask(taskId);
        
        if (result.success) {
            console.log(`[AnalysisPage] Task stopped: ${taskId}`);
            
            // 更新卡片状态
            const card = this.components.serviceGrid.cards.get(taskId);
            if (card) {
                card.updateStatus({ status: 'stopped' });
            }
        } else {
            console.error(`[AnalysisPage] Failed to stop task: ${result.error}`);
            alert(`停止失败: ${result.error}`);
        }
    }

    async stopProcess(processId) {
        console.log(`[AnalysisPage] Stopping process: ${processId}`);
        
        const result = await this.analysisManager.stopProcess(processId);
        
        if (result.success) {
            console.log(`[AnalysisPage] Process stopped: ${processId}`);
            
            // 更新所有卡片状态
            this.updateTaskStatuses();
        } else {
            console.error(`[AnalysisPage] Failed to stop process: ${result.error}`);
            alert(`停止失败: ${result.error}`);
        }
    }

    updateTaskStatuses() {
        if (this.components.serviceGrid) {
            this.components.serviceGrid.updateStatus();
        }
    }

    async refreshProcessList() {
        const processes = await this.analysisManager.getProcessList();
        if (this.components.processList) {
            this.components.processList.render(processes);
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.analysisPage = new AnalysisPage();
    window.analysisPage.init();
});
