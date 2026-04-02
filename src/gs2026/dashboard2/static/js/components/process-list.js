/**
 * ProcessList - 进程列表组件
 * 显示当前运行的所有进程
 * 【优化】支持统一显示任务名称和模块来源标识
 */

class ProcessList extends BaseComponent {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.processes = [];
        this.eventsBound = false;  // 标志位，避免重复绑定事件
    }

    renderTemplate() {
        if (this.processes.length === 0) {
            return `
                <div class="process-list-empty">
                    <div class="empty-icon">😴</div>
                    <div class="empty-text">暂无任务记录</div>
                </div>
            `;
        }

        const items = this.processes.map(proc => {
            // 兼容不同管理器的字段名（驼峰/下划线）
            const startTime = proc.startTime || proc.start_time;
            const moduleId = proc.moduleId || proc.module || 'unknown';
            const taskId = proc.taskId || proc.task_id || proc.serviceId || proc.service_id || '';
            
            const duration = this.formatDuration(startTime);
            const taskName = this.getTaskName(moduleId, taskId);
            const moduleTag = this.getModuleTag(moduleId);
            
            // 根据状态确定显示
            let statusBadge = '';
            const status = proc.status || 'unknown';
            if (status === 'running') {
                statusBadge = '<span class="status-badge running">运行中</span>';
            } else if (status === 'stopped') {
                statusBadge = '<span class="status-badge stopped">已停止</span>';
            } else if (status === 'executing') {
                statusBadge = '<span class="status-badge executing">执行中</span>';
            } else if (status === 'completed') {
                statusBadge = '<span class="status-badge completed">已完成</span>';
            } else {
                statusBadge = `<span class="status-badge">${status}</span>`;
            }

            return `
                <div class="process-item" data-process="${proc.process_id}" data-module="${moduleId}">
                    <div class="process-info">
                        ${moduleTag}
                        <span class="process-task">${taskName}</span>
                        ${statusBadge}
                        <span class="process-pid">PID:${proc.pid || '-'}</span>
                        <span class="process-duration">${duration}</span>
                    </div>
                    <button class="btn btn-stop-sm" data-action="stop" data-process="${proc.process_id}" ${status !== 'running' ? 'disabled' : ''}>
                        ⏹️
                    </button>
                </div>
            `;
        }).join('');

        // 统计各状态数量
        const runningCount = this.processes.filter(p => p.status === 'running').length;
        const totalCount = this.processes.length;

        return `
            <div class="process-list-header">
                <span class="process-count">任务: ${totalCount} (运行中: ${runningCount})</span>
                <button class="btn btn-stop-all" data-action="stopAll">全部停止</button>
            </div>
            <div class="process-items">
                ${items}
            </div>
        `;
    }

    bindEvents() {
        // 避免重复绑定事件
        if (this.eventsBound) {
            return;
        }
        this.eventsBound = true;
        
        // 使用事件委托，绑定到容器而不是单个按钮
        this.container.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-stop-sm');
            if (btn) {
                console.log('[DEBUG] Stop button clicked (delegated):', btn.dataset.process);
                const processId = btn.dataset.process;
                this.emit('stop', { processId });
            }
        });

        // 全部停止
        const stopAllBtn = this.$('.btn-stop-all');
        if (stopAllBtn) {
            stopAllBtn.addEventListener('click', () => {
                if (confirm('确定要停止所有进程吗？')) {
                    this.emit('stopAll');
                }
            });
        }
    }

    update(processes) {
        this.processes = processes || [];
        this.render();
    }

    formatDuration(startTime) {
        if (!startTime) return '';
        
        // 兼容多种时间格式：时间戳、ISO字符串、Date对象
        let startTimestamp;
        if (typeof startTime === 'number') {
            // 已经是时间戳（毫秒）
            startTimestamp = startTime;
        } else if (typeof startTime === 'string') {
            // ISO 格式字符串，如 "2026-04-02T19:30:00"
            startTimestamp = new Date(startTime).getTime();
        } else if (startTime instanceof Date) {
            // Date 对象
            startTimestamp = startTime.getTime();
        } else {
            return '';
        }
        
        // 检查是否为有效时间
        if (isNaN(startTimestamp) || startTimestamp <= 0) {
            return '';
        }
        
        const duration = Date.now() - startTimestamp;
        const seconds = Math.floor(duration / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);

        if (hours > 0) {
            return `${hours}h ${minutes % 60}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${seconds % 60}s`;
        } else {
            return `${seconds}s`;
        }
    }

    /**
     * 【新增】获取模块来源标识标签
     * @param {string} moduleId - 模块ID
     * @returns {string} HTML标签字符串
     */
    getModuleTag(moduleId) {
        // 数据采集模块
        const collectionModules = ['monitor', 'base', 'news', 'risk'];
        if (collectionModules.includes(moduleId)) {
            return '<span class="module-tag collection" title="数据采集模块">[采集]</span>';
        }
        // 数据分析模块 (包括 deepseek 等)
        if (moduleId === 'analysis' || moduleId === 'deepseek') {
            return '<span class="module-tag analysis" title="数据分析模块">[分析]</span>';
        }
        // 默认显示模块ID
        return `<span class="module-tag" title="${moduleId}">[${moduleId}]</span>`;
    }

    /**
     * 【优化】获取任务名称 - 统一从各管理器获取
     * @param {string} moduleId - 模块ID
     * @param {string} taskId - 任务ID
     * @returns {string} 任务显示名称
     */
    getTaskName(moduleId, taskId) {
        // 尝试从各个管理器获取任务名称
        const collectionManager = GS2026.getManager('collection');
        const analysisManager = GS2026.getManager('analysis');
        
        // 数据采集模块 (monitor, base, news, risk)
        if (['monitor', 'base', 'news', 'risk'].includes(moduleId) && collectionManager) {
            const task = collectionManager.getTaskConfig(moduleId, taskId);
            if (task?.name) {
                return task.name;
            }
            // 尝试从模块任务列表查找
            const module = collectionManager.getModule(moduleId);
            if (module?.tasks?.[taskId]?.name) {
                return module.tasks[taskId].name;
            }
            return taskId;
        }
        
        // 数据分析模块 (moduleId 可能是 'analysis' 或 'deepseek')
        if ((moduleId === 'analysis' || moduleId === 'deepseek') && analysisManager) {
            // 分析任务：从 service_id 提取 taskId (格式: analysis_{taskId})
            const actualTaskId = taskId?.replace('analysis_', '') || taskId;
            // 尝试从 deepseek 模块获取任务配置
            const module = analysisManager.getModule('deepseek');
            if (module?.tasks?.[actualTaskId]?.name) {
                return module.tasks[actualTaskId].name;
            }
            // 如果找不到，返回处理后的 taskId
            return actualTaskId;
        }
        
        return taskId;
    }
}
