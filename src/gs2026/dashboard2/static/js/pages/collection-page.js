/**
 * CollectionPage - 采集页面
 * 主页面控制器
 */

class CollectionPage {
    constructor() {
        this.collectionManager = null;
        this.components = {};
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;

        // 初始化采集管理器
        this.collectionManager = new CollectionManager();
        await this.collectionManager.init();
        
        // 同时初始化分析管理器（用于显示分析进程的任务名称）
        if (!GS2026.getManager('analysis')) {
            this.analysisManager = new AnalysisManager();
            await this.analysisManager.init();
        } else {
            this.analysisManager = GS2026.getManager('analysis');
        }

        // 初始化组件
        this.initComponents();

        // 绑定事件
        this.bindEvents();

        // 初始渲染
        this.render();

        this.initialized = true;
        console.log('CollectionPage initialized');
    }

    initComponents() {
        // Tab导航
        const modules = this.collectionManager.getModules();
        
        // 定义模块显示顺序：开市采集 -> 基础采集 -> 消息采集 -> 风险采集
        const moduleOrder = ['monitor', 'base', 'news', 'risk'];
        
        // 按顺序构建 tabs 数组
        const tabs = moduleOrder
            .filter(id => modules[id])  // 只包含存在的模块
            .map(id => ({
                id,
                name: modules[id].name,
                icon: modules[id].icon
            }));
        
        // 添加未在顺序中定义的其他模块
        Object.entries(modules).forEach(([id, mod]) => {
            if (!moduleOrder.includes(id)) {
                tabs.push({ id, name: mod.name, icon: mod.icon });
            }
        });

        this.components.tabNav = new TabNav('tab-nav', {
            tabs,
            defaultTab: 'monitor',
            on: {
                switch: (tabId) => this.switchModule(tabId)
            }
        });

        // 进程列表
        this.components.processList = new ProcessList('process-list', {
            on: {
                stop: ({ processId }) => this.stopProcess(processId),
                stopAll: () => this.stopAll()
            }
        });

        // 服务网格容器
        this.components.serviceGrid = {
            container: document.getElementById('service-grid'),
            cards: new Map(),

            render: (moduleId, tasksData) => {
                if (!this.components.serviceGrid.container) return;

                // 清空旧卡片
                this.components.serviceGrid.container.innerHTML = '';
                this.components.serviceGrid.cards.clear();

                // 支持两种格式：对象或列表
                const tasks = Array.isArray(tasksData) ? tasksData : Object.entries(tasksData).map(([id, config]) => ({ id, ...config }));

                // 创建新卡片（按列表顺序）
                tasks.forEach((task) => {
                    const taskId = task.id;
                    const config = task;
                    const cardId = `card-${taskId}`;
                    const cardDiv = document.createElement('div');
                    cardDiv.id = cardId;
                    this.components.serviceGrid.container.appendChild(cardDiv);

                    const status = this.getTaskStatus(moduleId, taskId);
                    const card = new ServiceCard(cardId, {
                        taskId,
                        config,
                        moduleId,
                        status,
                        on: {
                            start: ({ taskId, params }) => this.startTask(moduleId, taskId, params),
                            stop: ({ taskId }) => this.stopTask(moduleId, taskId)
                        }
                    });

                    card.render();
                    this.components.serviceGrid.cards.set(taskId, card);
                });
            },

            updateStatus: (processes) => {
                // 更新所有卡片状态
                this.components.serviceGrid.cards.forEach((card, taskId) => {
                    const status = processes.find(p => p.taskId === taskId);
                    if (status) {
                        card.updateStatus({ running: true, pid: status.pid });
                    } else {
                        card.updateStatus({ running: false });
                    }
                });
            }
        };
    }

    bindEvents() {
        // 监听管理器事件
        this.collectionManager.on('taskStarted', () => {
            this.refreshProcessList();
        });

        this.collectionManager.on('taskStopped', () => {
            this.refreshProcessList();
        });

        this.collectionManager.on('allStopped', () => {
            this.refreshProcessList();
            this.refreshServiceGrid();
        });

        this.collectionManager.on('statusRefreshed', (processes) => {
            this.components.processList.update(processes);
            this.components.serviceGrid.updateStatus(processes);
        });
    }

    render() {
        // 渲染Tab导航
        this.components.tabNav.render();

        // 渲染进程列表
        this.refreshProcessList();

        // 渲染默认模块
        this.switchModule('monitor');
    }

    switchModule(moduleId) {
        const tasks = this.collectionManager.getModuleTasks(moduleId);
        this.components.serviceGrid.render(moduleId, tasks);
    }

    async startTask(moduleId, taskId, params) {
        try {
            await this.collectionManager.startTask(moduleId, taskId, params);
            // 不显示弹窗，只在控制台记录
            console.log('[INFO] 启动成功');
        } catch (e) {
            console.error('[ERROR] 启动失败:', e.message);
            // 可选：显示错误提示（但不使用 alert）
            // GS2026.notify?.error?.('启动失败: ' + e.message);
        }
    }

    async stopTask(moduleId, taskId) {
        // 找到对应的进程ID
        const processes = this.collectionManager.getRunningTasks();
        const process = processes.find(p => p.moduleId === moduleId && p.taskId === taskId);

        if (process) {
            try {
                await this.collectionManager.stopTask(process.processId);
                console.log('[INFO] 停止成功');
            } catch (e) {
                console.error('[ERROR] 停止失败:', e.message);
            }
        }
    }

    async stopProcess(processId) {
        console.log('[DEBUG] stopProcess called:', processId);
        try {
            await this.collectionManager.stopTask(processId);
            console.log('[INFO] 停止成功');
        } catch (e) {
            console.error('[ERROR] 停止失败:', e.message);
        }
    }

    async stopAll() {
        try {
            const result = await this.collectionManager.stopAll();
            console.log('[INFO] 已停止', result.stopped, '个进程');
        } catch (e) {
            console.error('[ERROR] 停止失败:', e.message);
        }
    }

    refreshProcessList() {
        const processes = this.collectionManager.getRunningTasks();
        this.components.processList.update(processes);
    }

    refreshServiceGrid() {
        const processes = this.collectionManager.getRunningTasks();
        this.components.serviceGrid.updateStatus(processes);
    }

    getTaskStatus(moduleId, taskId) {
        const processes = this.collectionManager.getRunningTasks();
        const process = processes.find(p => p.moduleId === moduleId && p.taskId === taskId);
        if (!process) {
            return { status: 'stopped', running: false };
        }
        // 返回完整状态对象
        return {
            status: process.status,
            running: process.status === 'running',
            pid: process.pid,
            taskType: process.taskType
        };
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', () => {
    const page = new CollectionPage();
    page.init();
});
