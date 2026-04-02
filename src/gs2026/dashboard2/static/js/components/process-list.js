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
            const duration = this.formatDuration(proc.startTime);
            const taskName = this.getTaskName(proc.module, proc.taskId || proc.service_id);
            const moduleTag = this.getModuleTag(proc.module);
            
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
                <div class="process-item" data-process="${proc.process_id}" data-module="${proc.module}">
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
        const duration = Date.now() - startTime;
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
        const tags = {
            monitor: '<span class="module-tag collection" title="数据采集模块">[采集]</span>',
            base: '<span class="module-tag collection" title="数据采集模块">[采集]</span>',
            news: '<span class="module-tag collection" title="数据采集模块">[采集]</span>',
            risk: '<span class="module-tag collection" title="数据采集模块">[采集]</span>',
            analysis: '<span class="module-tag analysis" title="数据分析模块">[分析]</span>'
        };
        return tags[moduleId] || `<span class="module-tag" title="${moduleId}">[${moduleId}]</span>`;
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
        
        // 数据分析模块
        if (moduleId === 'analysis' && analysisManager) {
            // 分析任务：从 service_id 提取 taskId (格式: analysis_{taskId})
            const actualTaskId = taskId?.replace('analysis_', '') || taskId;
            const module = analysisManager.getModule('deepseek');
            const task = module?.tasks?.[actualTaskId];
            return task?.name || actualTaskId;
        }
        
        return taskId;
    }
}
