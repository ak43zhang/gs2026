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

            if (p.type === 'date_list') {
                return this.renderDateListParam(p, inputId);
            } else if (p.type === 'date') {
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

    // 渲染日期列表参数
    renderDateListParam(param, inputId) {
        return `
            <div class="param-row date-list-param" data-param-name="${param.name}">
                <label class="param-label">${param.label}</label>
                <div class="date-list-input-group">
                    <input type="date" id="${inputId}-picker" class="date-picker">
                    <button type="button" class="btn btn-add-date" data-param="${param.name}">➕ 添加</button>
                </div>
                <div class="date-list-container" id="${inputId}-list">
                    <div class="date-list-empty">暂无日期，请添加</div>
                </div>
                <input type="hidden" id="${inputId}" class="date-list-hidden" value="[]">
            </div>
        `;
    }

    bindEvents() {
        // 启动按钮
        const startBtn = this.$('.btn-start');
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                const params = this.getParams();
                this.isEditing = false; // 启动时重置编辑状态
                this.emit('start', { taskId: this.taskId, params });
            });
        }

        // 停止按钮
        const stopBtn = this.$('.btn-stop');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => {
                this.isEditing = false; // 停止时重置编辑状态
                this.emit('stop', { taskId: this.taskId });
            });
        }
        
        // 日期列表：添加按钮
        const addDateBtn = this.$(`.btn-add-date`);
        if (addDateBtn) {
            addDateBtn.addEventListener('click', () => {
                const paramName = addDateBtn.dataset.param;
                const pickerId = `param-${this.taskId}-${paramName}-picker`;
                const picker = document.getElementById(pickerId);
                const dateValue = picker?.value;
                
                if (!dateValue) {
                    alert('请先选择日期');
                    return;
                }
                
                this.addDateToList(paramName, dateValue);
                picker.value = ''; // 清空选择器
            });
        }
        
        // 日期列表：删除按钮（事件委托）
        const dateListContainer = this.$(`.date-list-container`);
        if (dateListContainer) {
            dateListContainer.addEventListener('click', (e) => {
                if (e.target.classList.contains('btn-remove-date')) {
                    const dateValue = e.target.dataset.date;
                    const paramName = e.target.dataset.param;
                    this.removeDateFromList(paramName, dateValue);
                }
            });
        }
        
        // 编辑锁定：输入框获得焦点时锁定，失去焦点时延迟解锁
        const inputs = this.$$(`.service-params input`);
        inputs.forEach(input => {
            // 跳过日期选择器和隐藏字段
            if (input.classList.contains('date-picker') || input.type === 'hidden') {
                return;
            }
            
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

    // 添加日期到列表
    addDateToList(paramName, dateValue) {
        // 设置编辑状态，防止状态更新导致重新渲染
        this.isEditing = true;
        
        const hiddenInputId = `param-${this.taskId}-${paramName}`;
        const hiddenInput = document.getElementById(hiddenInputId);
        const listContainerId = `param-${this.taskId}-${paramName}-list`;
        const listContainer = document.getElementById(listContainerId);
        
        if (!hiddenInput || !listContainer) {
            this.isEditing = false;
            return;
        }
        
        // 获取当前列表
        let dateList = [];
        try {
            dateList = JSON.parse(hiddenInput.value || '[]');
        } catch (e) {
            dateList = [];
        }
        
        // 检查是否已存在
        if (dateList.includes(dateValue)) {
            alert('该日期已存在');
            this.isEditing = false;
            return;
        }
        
        // 添加日期
        dateList.push(dateValue);
        dateList.sort(); // 按日期排序
        hiddenInput.value = JSON.stringify(dateList);
        
        // 更新显示
        this.renderDateList(listContainer, paramName, dateList);
        
        // 保持编辑状态，不自动解锁
        // 用户离开页面或点击启动/停止时才解锁
    }

    // 从列表删除日期
    removeDateFromList(paramName, dateValue) {
        // 设置编辑状态，防止状态更新导致重新渲染
        this.isEditing = true;
        
        const hiddenInputId = `param-${this.taskId}-${paramName}`;
        const hiddenInput = document.getElementById(hiddenInputId);
        const listContainerId = `param-${this.taskId}-${paramName}-list`;
        const listContainer = document.getElementById(listContainerId);
        
        if (!hiddenInput || !listContainer) {
            this.isEditing = false;
            return;
        }
        
        // 获取当前列表
        let dateList = [];
        try {
            dateList = JSON.parse(hiddenInput.value || '[]');
        } catch (e) {
            dateList = [];
        }
        
        // 删除日期
        dateList = dateList.filter(d => d !== dateValue);
        hiddenInput.value = JSON.stringify(dateList);
        
        // 更新显示
        this.renderDateList(listContainer, paramName, dateList);
        
        // 保持编辑状态，不自动解锁
    }

    // 渲染日期列表
    renderDateList(container, paramName, dateList) {
        if (dateList.length === 0) {
            container.innerHTML = '<div class="date-list-empty">暂无日期，请添加</div>';
            return;
        }
        
        container.innerHTML = dateList.map(date => `
            <div class="date-list-item">
                <span class="date-value">📅 ${date}</span>
                <button type="button" class="btn-remove-date" data-date="${date}" data-param="${paramName}">❌</button>
            </div>
        `).join('');
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
            } else if (input.classList.contains('date-list-hidden')) {
                // 日期列表类型，解析JSON数组
                try {
                    params[name] = JSON.parse(input.value || '[]');
                } catch (e) {
                    params[name] = [];
                }
            } else {
                params[name] = input.value;
            }
        });

        return params;
    }

    updateStatus(status) {
        // 保存新状态
        this.status = status;
        
        // 如果正在编辑，只更新状态指示器，不重新渲染整个卡片
        if (this.isEditing) {
            console.log(`[DEBUG] ${this.taskId} updating status only while editing`);
            this.updateStatusOnly(status);
            return;
        }
        
        // 正常重新渲染
        this.render({ taskId: this.taskId, config: this.config, status });
    }
    
    // 仅更新状态指示器（不重新渲染参数区域）
    updateStatusOnly(status) {
        const card = this.$('.service-card');
        if (!card) return;
        
        // 更新状态类
        card.classList.remove('running', 'executing', 'completed', 'stopped');
        let statusClass = 'stopped';
        let statusText = '已停止';
        
        if (status.status === 'running') {
            statusClass = 'running';
            statusText = '运行中';
        } else if (status.status === 'executing') {
            statusClass = 'executing';
            statusText = '执行中';
        } else if (status.status === 'completed') {
            statusClass = 'completed';
            statusText = '已完成';
        }
        
        card.classList.add(statusClass);
        
        // 更新状态文字
        const statusTextEl = this.$('.status-text');
        if (statusTextEl) {
            statusTextEl.textContent = statusText;
        }
        
        // 更新PID显示
        const pidEl = this.$('.service-pid');
        if (pidEl) {
            if (status.pid) {
                pidEl.textContent = `PID:${status.pid}`;
            } else {
                pidEl.textContent = '';
            }
        }
        
        // 更新按钮状态
        const startBtn = this.$('.btn-start');
        const stopBtn = this.$('.btn-stop');
        
        if (startBtn) {
            startBtn.disabled = status.status === 'running' || status.status === 'executing';
        }
        if (stopBtn) {
            stopBtn.disabled = status.status !== 'running';
        }
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
