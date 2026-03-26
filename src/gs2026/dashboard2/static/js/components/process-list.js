/**
 * ProcessList - 进程列表组件
 * 显示当前运行的所有进程
 */

class ProcessList extends BaseComponent {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.processes = [];
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
            const moduleName = this.getModuleName(proc.module);
            const taskName = this.getTaskName(proc.module, proc.taskId || proc.service_id);
            
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
                <div class="process-item" data-process="${proc.process_id}">
                    <div class="process-info">
                        <span class="process-module">${moduleName}</span>
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

    getModuleName(moduleId) {
        const names = {
            monitor: '开市采集',
            base: '基础采集',
            news: '消息采集',
            risk: '风险采集'
        };
        return names[moduleId] || moduleId;
    }

    getTaskName(moduleId, taskId) {
        // 从配置中获取任务名称
        const manager = GS2026.getManager('collection');
        const task = manager?.getTaskConfig(moduleId, taskId);
        return task?.name || taskId;
    }
}
