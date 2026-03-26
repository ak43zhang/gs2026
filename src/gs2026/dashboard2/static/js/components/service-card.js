/**
 * ServiceCard - 服务卡片组件
 * 显示单个采集/监控任务卡片
 */

class ServiceCard extends BaseComponent {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.taskId = options.taskId;
        this.config = options.config;
        this.moduleId = options.moduleId;
        this.status = options.status || { running: false };
        
        // 编辑锁定状态
        this.isEditing = false;
        this.editTimeout = null;
    }

    renderTemplate() {
        const icon = this.getIcon(this.taskId);
        
        // 根据状态确定显示
        let statusClass = 'stopped';
        let statusText = '已停止';
        
        if (this.status.status === 'running') {
            statusClass = 'running';
            statusText = '运行中';
        } else if (this.status.status === 'executing') {
            statusClass = 'executing';
            statusText = '执行中';
        } else if (this.status.status === 'completed') {
            statusClass = 'completed';
            statusText = '已完成';
        }
        
        const params = this.config.params || [];

        return `
            <div class="service-card ${statusClass} ${this.isEditing ? 'editing' : ''}" data-task="${this.taskId}">
                <div class="service-header">
                    <span class="service-icon">${icon}</span>
                    <span class="service-name">${this.config.name}</span>
                    ${this.isEditing ? '<span class="edit-indicator">✏️ 编辑中</span>' : ''}
                </div>
                <div class="service-status">
                    <span class="status-dot"></span>
                    <span class="status-text">${statusText}</span>
                    ${this.status.pid ? `<span class="service-pid">PID:${this.status.pid}</span>` : ''}
                </div>
                <div class="service-params" id="params-${this.taskId}">
                    ${this.renderParams(params)}
                </div>
                <div class="service-actions">
                    <button class="btn btn-start" data-action="start" ${this.status.status === 'running' || this.status.status === 'executing' ? 'disabled' : ''}>
                        ▶️ 启动
                    </button>
                    <button class="btn btn-stop" data-action="stop" ${this.status.status !== 'running' ? 'disabled' : ''}>
                        ⏹️ 停止
                    </button>
                </div>
            </div>
        `;
    }

    renderParams(params) {
        if (!params || params.length === 0) {
            return '<div class="param-hint">无需参数</div>';
        }

        const today = GS2026.utils.formatDate(new Date(), 'YYYY-MM-DD');

        return params.map(p => {
            const inputId = `param-${this.taskId}-${p.name}`;
            const value = p.default !== undefined ? p.default : (p.type === 'date' ? today : '');

            if (p.type === 'date') {
                return `
                    <div class="param-row">
                        <label class="param-label">${p.label}</label>
                        <input type="date" id="${inputId}" value="${value}" ${p.required ? 'required' : ''}>
                    </div>
                `;
            } else if (p.type === 'datetime') {
                return `
                    <div class="param-row">
                        <label class="param-label">${p.label}</label>
                        <input type="datetime-local" id="${inputId}" value="${value}" ${p.required ? 'required' : ''}>
                    </div>
                `;
            } else if (p.type === 'number') {
                return `
                    <div class="param-row">
                        <label class="param-label">${p.label}</label>
                        <input type="number" id="${inputId}" value="${value}" ${p.required ? 'required' : ''}>
                    </div>
                `;
            } else if (p.type === 'boolean') {
                return `
                    <div class="param-row">
                        <label class="param-label">${p.label}</label>
                        <input type="checkbox" id="${inputId}" ${value ? 'checked' : ''}>
                    </div>
                `;
            } else {
                return `
                    <div class="param-row">
                        <label class="param-label">${p.label}</label>
                        <input type="text" id="${inputId}" value="${value}" ${p.required ? 'required' : ''}>
                    </div>
                `;
            }
        }).join('');
    }

    bindEvents() {
        // 启动按钮
        const startBtn = this.$('.btn-start');
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                const params = this.getParams();
                this.emit('start', { taskId: this.taskId, params });
            });
        }

        // 停止按钮
        const stopBtn = this.$('.btn-stop');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => {
                this.emit('stop', { taskId: this.taskId });
            });
        }
        
        // 编辑锁定：输入框获得焦点时锁定，失去焦点时延迟解锁
        const inputs = this.$$('.service-params input');
        inputs.forEach(input => {
            input.addEventListener('focus', () => {
                this.isEditing = true;
                console.log(`[DEBUG] ${this.taskId} editing locked`);
                // 清除之前的解锁定时器
                if (this.editTimeout) {
                    clearTimeout(this.editTimeout);
                    this.editTimeout = null;
                }
            });
            
            input.addEventListener('blur', () => {
                // 延迟解锁，避免快速切换时的闪烁
                this.editTimeout = setTimeout(() => {
                    this.isEditing = false;
                    console.log(`[DEBUG] ${this.taskId} editing unlocked`);
                }, 500);
            });
        });
    }

    getParams() {
        const params = {};
        const inputs = this.$$(`.service-params input`);
        
        inputs.forEach(input => {
            const name = input.id.replace(`param-${this.taskId}-`, '');
            if (input.type === 'checkbox') {
                params[name] = input.checked;
            } else if (input.type === 'number') {
                params[name] = parseFloat(input.value) || 0;
            } else {
                params[name] = input.value;
            }
        });

        return params;
    }

    updateStatus(status) {
        // 如果正在编辑，不更新（避免重置输入框）
        if (this.isEditing) {
            console.log(`[DEBUG] ${this.taskId} skipping update while editing`);
            // 只更新状态，不重新渲染
            this.status = status;
            return;
        }
        
        this.status = status;
        this.render({ taskId: this.taskId, config: this.config, status });
    }

    getIcon(taskId) {
        const icons = {
            stock: '📈', bond: '💹', industry: '🏭', dp_signal: '📊', gp_zq_signal: '🔗',
            wencai_base: '🔍', wencai_hot: '🔥', ztb: '📈', zt_zb: '💥',
            zskj: '📚', today_lhb: '🐉', rzrq: '💰', gsdt: '🏢',
            history_lhb: '📜', risk_tdx: '⚠️', industry_ths: '🏭', industry_code_component_ths: '📋'
        };
        return icons[taskId] || '📋';
    }
}
