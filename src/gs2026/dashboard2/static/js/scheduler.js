/**
 * Dashboard2 调度中心前端脚本
 */

// 全局状态
let jobsData = [];
let executionsData = [];
let chainsData = [];
let currentTab = 'jobs';

// 任务类型映射
const jobTypeMap = {
    'redis_cache': 'Redis缓存',
    'dashboard_task': 'Dashboard任务',
    'python_script': 'Python脚本',
    'chain': '调度链'
};

// 状态映射
const statusMap = {
    'enabled': { text: '已启用', class: 'tag-enabled' },
    'disabled': { text: '已禁用', class: 'tag-disabled' },
    'running': { text: '运行中', class: 'tag-running' },
    'error': { text: '错误', class: 'tag-error' },
    'success': { text: '成功', class: 'tag-success' },
    'failed': { text: '失败', class: 'tag-failed' },
    'pending': { text: '等待中', class: 'tag-pending' }
};

// 初始化
function initScheduler() {
    checkSchedulerStatus();
    loadJobs();
    loadExecutions();
    loadChains();
    
    // 定时刷新
    setInterval(() => {
        checkSchedulerStatus();
        if (currentTab === 'jobs') loadJobs();
        if (currentTab === 'executions') loadExecutions();
        if (currentTab === 'chains') loadChains();
    }, 10000);
}

// 检查调度器状态
async function checkSchedulerStatus() {
    try {
        const response = await fetch('/api/scheduler/status');
        const data = await response.json();
        
        if (data.code === 200) {
            const status = data.data.running ? 'running' : 'stopped';
            const statusEl = document.getElementById('scheduler-status');
            const statusText = document.getElementById('status-text');
            const btnStart = document.getElementById('btn-start');
            const btnStop = document.getElementById('btn-stop');
            
            statusEl.className = `status-indicator status-${status}`;
            statusText.textContent = data.data.running ? '运行中' : '已停止';
            
            if (data.data.running) {
                btnStart.style.display = 'none';
                btnStop.style.display = 'inline-block';
            } else {
                btnStart.style.display = 'inline-block';
                btnStop.style.display = 'none';
            }
            
            // 更新统计
            document.getElementById('stat-running-executions').textContent = data.data.running_executions;
        }
    } catch (error) {
        console.error('Failed to check scheduler status:', error);
    }
}

// 启动调度器
async function startScheduler() {
    try {
        const response = await fetch('/api/scheduler/start', { method: 'POST' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('调度器已启动', 'success');
            checkSchedulerStatus();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('启动失败: ' + error.message, 'error');
    }
}

// 停止调度器
async function stopScheduler() {
    if (!confirm('确定要停止调度器吗？正在运行的任务将被中断。')) {
        return;
    }
    
    try {
        const response = await fetch('/api/scheduler/stop', { method: 'POST' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('调度器已停止', 'success');
            checkSchedulerStatus();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('停止失败: ' + error.message, 'error');
    }
}

// 刷新所有数据
function refreshAll() {
    checkSchedulerStatus();
    loadJobs();
    loadExecutions();
    loadChains();
    showMessage('数据已刷新', 'success');
}

// 切换标签页
function switchTab(tab) {
    currentTab = tab;
    
    // 更新标签样式
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    
    event.target.classList.add('active');
    document.getElementById(`tab-${tab}`).classList.add('active');
    
    // 加载对应数据
    if (tab === 'jobs') loadJobs();
    if (tab === 'executions') loadExecutions();
    if (tab === 'chains') loadChains();
}

// 加载任务列表
async function loadJobs() {
    try {
        const jobType = document.getElementById('filter-job-type')?.value || '';
        const status = document.getElementById('filter-job-status')?.value || '';
        
        let url = '/api/scheduler/jobs';
        const params = [];
        if (jobType) params.push(`job_type=${jobType}`);
        if (status) params.push(`status=${status}`);
        if (params.length > 0) url += '?' + params.join('&');
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.code === 200) {
            jobsData = data.data.jobs;
            renderJobsTable(jobsData);
            
            // 更新统计
            document.getElementById('stat-total-jobs').textContent = jobsData.length;
            document.getElementById('stat-enabled-jobs').textContent = jobsData.filter(j => j.status === 'enabled').length;
            
            // 更新执行记录过滤器的任务选项
            updateExecutionJobFilter(jobsData);
        }
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

// 渲染任务表格
function renderJobsTable(jobs) {
    const tbody = document.getElementById('jobs-table-body');
    
    if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #999;">暂无任务</td></tr>';
        return;
    }
    
    tbody.innerHTML = jobs.map(job => {
        const statusInfo = statusMap[job.status] || { text: job.status, class: '' };
        const triggerType = job.trigger_type || 'cron';
        const triggerConfig = typeof job.trigger_config === 'object' ? job.trigger_config : {};
        let triggerDesc = triggerType;
        if (triggerType === 'cron') {
            triggerDesc = triggerConfig.minute !== undefined ? 
                `${triggerConfig.hour || '*'}:${triggerConfig.minute || '*'}` : 'Cron';
        }
        
        return `
            <tr>
                <td>${job.job_id}</td>
                <td>${job.job_name}</td>
                <td>${jobTypeMap[job.job_type] || job.job_type}</td>
                <td>${triggerDesc}</td>
                <td><span class="tag ${statusInfo.class}">${statusInfo.text}</span></td>
                <td>${job.last_run_time ? formatDateTime(job.last_run_time) : '-'}</td>
                <td>${job.run_count || 0}</td>
                <td class="actions">
                    <button class="btn-primary btn-sm" onclick="runJobNow('${job.job_id}')">▶</button>
                    <button class="btn-secondary btn-sm" onclick="editJob('${job.job_id}')">编辑</button>
                    <button class="btn-secondary btn-sm" onclick="toggleJob('${job.job_id}', ${job.status !== 'enabled'})">
                        ${job.status === 'enabled' ? '禁用' : '启用'}
                    </button>
                    <button class="btn-danger btn-sm" onclick="deleteJob('${job.job_id}')">删除</button>
                </td>
            </tr>
        `;
    }).join('');
}

// 更新执行记录的任务过滤器
function updateExecutionJobFilter(jobs) {
    const select = document.getElementById('filter-execution-job');
    const currentValue = select.value;
    
    select.innerHTML = '<option value="">全部任务</option>';
    jobs.forEach(job => {
        const option = document.createElement('option');
        option.value = job.job_id;
        option.textContent = job.job_name;
        select.appendChild(option);
    });
    
    select.value = currentValue;
}

// 打开任务模态框
function openJobModal(jobId = null) {
    const modal = document.getElementById('job-modal');
    const title = document.getElementById('job-modal-title');
    const form = document.getElementById('job-form');
    
    form.reset();
    document.getElementById('job-id-hidden').value = '';
    
    if (jobId) {
        // 编辑模式
        title.textContent = '✏️ 编辑任务';
        const job = jobsData.find(j => j.job_id === jobId);
        if (job) {
            document.getElementById('job-id-hidden').value = job.job_id;
            document.getElementById('job-id').value = job.job_id;
            document.getElementById('job-name').value = job.job_name;
            document.getElementById('job-type').value = job.job_type;
            document.getElementById('trigger-type').value = job.trigger_type;
            document.getElementById('job-description').value = job.description || '';
            
            onJobTypeChange();
            onTriggerTypeChange();
            
            // 填充类型特定配置
            const jobConfig = typeof job.job_config === 'object' ? job.job_config : {};
            const triggerConfig = typeof job.trigger_config === 'object' ? job.trigger_config : {};
            
            if (job.job_type === 'redis_cache') {
                document.getElementById('redis-cache-type').value = jobConfig.cache_type || '';
                document.getElementById('redis-function').value = jobConfig.function || '';
                document.getElementById('redis-module').value = jobConfig.module || '';
            } else if (job.job_type === 'dashboard_task') {
                document.getElementById('dashboard-category').value = jobConfig.task_category || '';
                document.getElementById('dashboard-task-id').value = jobConfig.task_id || '';
            } else if (job.job_type === 'python_script') {
                document.getElementById('python-script').value = jobConfig.script_path || '';
                document.getElementById('python-function').value = jobConfig.function || 'main';
                document.getElementById('python-timeout').value = jobConfig.timeout || 3600;
            } else if (job.job_type === 'chain') {
                document.getElementById('chain-steps').value = JSON.stringify(jobConfig.steps || [], null, 2);
            }
            
            // 填充触发器配置
            if (job.trigger_type === 'cron') {
                const cronParts = [
                    triggerConfig.second || '0',
                    triggerConfig.minute || '*',
                    triggerConfig.hour || '*',
                    triggerConfig.day || '*',
                    triggerConfig.month || '*',
                    triggerConfig.day_of_week || '*'
                ];
                document.getElementById('cron-expression').value = cronParts.join(' ');
            } else if (job.trigger_type === 'interval') {
                document.getElementById('interval-hours').value = triggerConfig.hours || 0;
                document.getElementById('interval-minutes').value = triggerConfig.minutes || 0;
            }
        }
    } else {
        // 新建模式
        title.textContent = '➕ 新建任务';
        document.getElementById('job-id').disabled = false;
    }
    
    modal.classList.add('active');
}

// 关闭任务模态框
function closeJobModal() {
    document.getElementById('job-modal').classList.remove('active');
}

// 任务类型改变
function onJobTypeChange() {
    const jobType = document.getElementById('job-type').value;
    
    // 隐藏所有配置
    document.querySelectorAll('.job-type-config').forEach(el => el.style.display = 'none');
    
    // 显示对应配置
    if (jobType === 'redis_cache') {
        document.getElementById('redis-config').style.display = 'block';
    } else if (jobType === 'dashboard_task') {
        document.getElementById('dashboard-config').style.display = 'block';
    } else if (jobType === 'python_script') {
        document.getElementById('python-config').style.display = 'block';
    } else if (jobType === 'chain') {
        document.getElementById('chain-config').style.display = 'block';
    }
}

// 触发器类型改变
function onTriggerTypeChange() {
    const triggerType = document.getElementById('trigger-type').value;
    
    // 隐藏所有触发器配置
    document.querySelectorAll('.trigger-type-config').forEach(el => el.style.display = 'none');
    
    // 显示对应配置
    if (triggerType === 'cron') {
        document.getElementById('cron-config').style.display = 'block';
    } else if (triggerType === 'interval') {
        document.getElementById('interval-config').style.display = 'block';
    } else if (triggerType === 'date') {
        document.getElementById('date-config').style.display = 'block';
    }
}

// 保存任务
async function saveJob() {
    const jobIdHidden = document.getElementById('job-id-hidden').value;
    const jobId = document.getElementById('job-id').value;
    const jobName = document.getElementById('job-name').value;
    const jobType = document.getElementById('job-type').value;
    const triggerType = document.getElementById('trigger-type').value;
    const description = document.getElementById('job-description').value;
    
    if (!jobId || !jobName || !jobType) {
        showMessage('请填写必填字段', 'error');
        return;
    }
    
    // 构建任务配置
    let jobConfig = {};
    if (jobType === 'redis_cache') {
        jobConfig = {
            cache_type: document.getElementById('redis-cache-type').value,
            function: document.getElementById('redis-function').value,
            module: document.getElementById('redis-module').value,
            params: { date: null }
        };
    } else if (jobType === 'dashboard_task') {
        jobConfig = {
            task_category: document.getElementById('dashboard-category').value,
            task_id: document.getElementById('dashboard-task-id').value,
            params: { date: null }
        };
    } else if (jobType === 'python_script') {
        jobConfig = {
            script_path: document.getElementById('python-script').value,
            function: document.getElementById('python-function').value,
            params: { base_date: null },
            working_dir: 'F:/pyworkspace2026/gs2026',
            timeout: parseInt(document.getElementById('python-timeout').value) || 3600
        };
    } else if (jobType === 'chain') {
        try {
            jobConfig = {
                steps: JSON.parse(document.getElementById('chain-steps').value || '[]')
            };
        } catch (e) {
            showMessage('链步骤JSON格式错误', 'error');
            return;
        }
    }
    
    // 构建触发器配置
    let triggerConfig = {};
    if (triggerType === 'cron') {
        const cronParts = document.getElementById('cron-expression').value.split(' ');
        triggerConfig = {
            second: cronParts[0] || '0',
            minute: cronParts[1] || '*',
            hour: cronParts[2] || '*',
            day: cronParts[3] || '*',
            month: cronParts[4] || '*',
            day_of_week: cronParts[5] || '*'
        };
    } else if (triggerType === 'interval') {
        triggerConfig = {
            hours: parseInt(document.getElementById('interval-hours').value) || 0,
            minutes: parseInt(document.getElementById('interval-minutes').value) || 0
        };
    } else if (triggerType === 'date') {
        triggerConfig = {
            run_date: document.getElementById('date-time').value
        };
    }
    
    const payload = {
        job_id: jobId,
        job_name: jobName,
        job_type: jobType,
        job_config: jobConfig,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        description: description,
        status: 'enabled'
    };
    
    try {
        const url = jobIdHidden ? `/api/scheduler/jobs/${jobIdHidden}` : '/api/scheduler/jobs';
        const method = jobIdHidden ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage(jobIdHidden ? '任务已更新' : '任务已创建', 'success');
            closeJobModal();
            loadJobs();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('保存失败: ' + error.message, 'error');
    }
}

// 编辑任务
function editJob(jobId) {
    openJobModal(jobId);
}

// 立即执行任务
async function runJobNow(jobId) {
    try {
        const response = await fetch(`/api/scheduler/jobs/${jobId}/run`, { method: 'POST' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('任务已触发', 'success');
            setTimeout(() => loadExecutions(), 1000);
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('执行失败: ' + error.message, 'error');
    }
}

// 切换任务状态
async function toggleJob(jobId, enable) {
    try {
        const response = await fetch(`/api/scheduler/jobs/${jobId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enable })
        });
        
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage(enable ? '任务已启用' : '任务已禁用', 'success');
            loadJobs();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('操作失败: ' + error.message, 'error');
    }
}

// 删除任务
async function deleteJob(jobId) {
    if (!confirm(`确定要删除任务 "${jobId}" 吗？`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/scheduler/jobs/${jobId}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('任务已删除', 'success');
            loadJobs();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    }
}

// 加载执行记录
async function loadExecutions() {
    try {
        const jobId = document.getElementById('filter-execution-job')?.value || '';
        
        let url = '/api/scheduler/executions?limit=50';
        if (jobId) url += `&job_id=${jobId}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.code === 200) {
            executionsData = data.data.executions;
            renderExecutionsTable(executionsData);
            
            // 更新今日执行统计
            const today = new Date().toDateString();
            const todayExecutions = executionsData.filter(e => 
                new Date(e.start_time).toDateString() === today
            );
            document.getElementById('stat-today-executions').textContent = todayExecutions.length;
        }
    } catch (error) {
        console.error('Failed to load executions:', error);
    }
}

// 渲染执行记录表格
function renderExecutionsTable(executions) {
    const tbody = document.getElementById('executions-table-body');
    
    if (executions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 40px; color: #999;">暂无执行记录</td></tr>';
        return;
    }
    
    tbody.innerHTML = executions.map(exec => {
        const statusInfo = statusMap[exec.status] || { text: exec.status, class: '' };
        const duration = exec.duration_seconds ? `${exec.duration_seconds}s` : '-';
        
        return `
            <tr>
                <td>${exec.execution_id}</td>
                <td>${exec.job_id}</td>
                <td>${exec.trigger_type}</td>
                <td>${formatDateTime(exec.start_time)}</td>
                <td>${duration}</td>
                <td><span class="tag ${statusInfo.class}">${statusInfo.text}</span></td>
                <td class="actions">
                    <button class="btn-secondary btn-sm" onclick="viewExecution('${exec.execution_id}')">详情</button>
                </td>
            </tr>
        `;
    }).join('');
}

// 查看执行详情
async function viewExecution(executionId) {
    try {
        const response = await fetch(`/api/scheduler/executions/${executionId}`);
        const data = await response.json();
        
        if (data.code === 200) {
            const exec = data.data;
            const statusInfo = statusMap[exec.status] || { text: exec.status, class: '' };
            
            const detailHtml = `
                <div class="form-row">
                    <div class="form-group">
                        <label>执行ID</label>
                        <input type="text" value="${exec.execution_id}" readonly>
                    </div>
                    <div class="form-group">
                        <label>任务ID</label>
                        <input type="text" value="${exec.job_id}" readonly>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>触发方式</label>
                        <input type="text" value="${exec.trigger_type}" readonly>
                    </div>
                    <div class="form-group">
                        <label>状态</label>
                        <span class="tag ${statusInfo.class}">${statusInfo.text}</span>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>开始时间</label>
                        <input type="text" value="${formatDateTime(exec.start_time)}" readonly>
                    </div>
                    <div class="form-group">
                        <label>结束时间</label>
                        <input type="text" value="${exec.end_time ? formatDateTime(exec.end_time) : '-'}" readonly>
                    </div>
                </div>
                <div class="form-group">
                    <label>结果消息</label>
                    <textarea rows="3" readonly>${exec.result_message || '-'}</textarea>
                </div>
            `;
            
            document.getElementById('execution-detail').innerHTML = detailHtml;
            document.getElementById('execution-log').textContent = exec.output_log || '无日志输出';
            
            document.getElementById('execution-modal').classList.add('active');
        }
    } catch (error) {
        showMessage('加载详情失败: ' + error.message, 'error');
    }
}

// 关闭执行详情模态框
function closeExecutionModal() {
    document.getElementById('execution-modal').classList.remove('active');
}

// 加载调度链
async function loadChains() {
    try {
        const response = await fetch('/api/scheduler/chains');
        const data = await response.json();
        
        if (data.code === 200) {
            chainsData = data.data.chains;
            renderChainsList(chainsData);
        }
    } catch (error) {
        console.error('Failed to load chains:', error);
    }
}

// 渲染调度链列表
function renderChainsList(chains) {
    const container = document.getElementById('chains-list');
    
    if (chains.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔗</div><div>暂无调度链</div></div>';
        return;
    }
    
    container.innerHTML = chains.map(chain => {
        const jobConfig = typeof chain.job_config === 'object' ? chain.job_config : {};
        const steps = jobConfig.steps || [];
        
        const stepsHtml = steps.map((step, index) => `
            <div class="chain-node ${index === 0 ? 'active' : ''}">
                <span>${index + 1}. ${step.job_id}</span>
            </div>
            ${index < steps.length - 1 ? '<span class="chain-arrow">→</span>' : ''}
        `).join('');
        
        return `
            <div class="card">
                <div class="card-header">
                    <div>
                        <span class="card-title">${chain.job_name}</span>
                        <span style="color: #999; margin-left: 10px;">(${chain.job_id})</span>
                    </div>
                    <div class="actions">
                        <button class="btn-success btn-sm" onclick="runChain('${chain.job_id}')">▶ 执行</button>
                        <button class="btn-danger btn-sm" onclick="deleteChain('${chain.job_id}')">删除</button>
                    </div>
                </div>
                <div class="chain-visual">
                    ${stepsHtml || '<span style="color: #999;">无步骤</span>'}
                </div>
                <div style="color: #666; font-size: 13px; margin-top: 10px;">
                    ${chain.description || '无描述'}
                </div>
            </div>
        `;
    }).join('');
}

// 打开调度链模态框
function openChainModal() {
    document.getElementById('chain-modal').classList.add('active');
    document.getElementById('chain-form').reset();
    document.getElementById('chain-steps-container').innerHTML = '';
    addChainStep();
}

// 关闭调度链模态框
function closeChainModal() {
    document.getElementById('chain-modal').classList.remove('active');
}

// 添加链步骤
function addChainStep() {
    const container = document.getElementById('chain-steps-container');
    const index = container.children.length;
    
    const stepDiv = document.createElement('div');
    stepDiv.className = 'form-row';
    stepDiv.style.marginBottom = '10px';
    stepDiv.innerHTML = `
        <div class="form-group" style="flex: 2;">
            <select class="chain-step-job" style="width: 100%; padding: 8px;">
                <option value="">选择任务</option>
                ${jobsData.map(j => `<option value="${j.job_id}">${j.job_name} (${j.job_id})</option>`).join('')}
            </select>
        </div>
        <div class="form-group" style="flex: 1;">
            <select class="chain-step-wait" style="width: 100%; padding: 8px;">
                <option value="true">等待完成</option>
                <option value="false">不等待</option>
            </select>
        </div>
        <div class="form-group" style="flex: 0;">
            <button type="button" class="btn-danger btn-sm" onclick="this.closest('.form-row').remove()">删除</button>
        </div>
    `;
    
    container.appendChild(stepDiv);
}

// 保存调度链
async function saveChain() {
    const chainId = document.getElementById('chain-id').value;
    const chainName = document.getElementById('chain-name').value;
    const chainCron = document.getElementById('chain-cron').value;
    const description = document.getElementById('chain-description').value;
    
    if (!chainId || !chainName) {
        showMessage('请填写必填字段', 'error');
        return;
    }
    
    // 收集步骤
    const steps = [];
    document.querySelectorAll('#chain-steps-container .form-row').forEach(row => {
        const jobId = row.querySelector('.chain-step-job').value;
        const wait = row.querySelector('.chain-step-wait').value === 'true';
        if (jobId) {
            steps.push({ job_id: jobId, wait: wait });
        }
    });
    
    if (steps.length === 0) {
        showMessage('请至少添加一个步骤', 'error');
        return;
    }
    
    const cronParts = chainCron.split(' ');
    const payload = {
        job_id: chainId,
        job_name: chainName,
        job_config: { steps: steps },
        trigger_type: 'cron',
        trigger_config: {
            second: cronParts[0] || '0',
            minute: cronParts[1] || '*',
            hour: cronParts[2] || '*',
            day: cronParts[3] || '*',
            month: cronParts[4] || '*',
            day_of_week: cronParts[5] || '*'
        },
        description: description,
        status: 'enabled'
    };
    
    try {
        const response = await fetch('/api/scheduler/chains', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('调度链已创建', 'success');
            closeChainModal();
            loadChains();
            loadJobs();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('保存失败: ' + error.message, 'error');
    }
}

// 执行调度链
async function runChain(chainId) {
    try {
        const response = await fetch(`/api/scheduler/chains/${chainId}/run`, { method: 'POST' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('调度链已触发', 'success');
            setTimeout(() => loadExecutions(), 1000);
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('执行失败: ' + error.message, 'error');
    }
}

// 删除调度链
async function deleteChain(chainId) {
    if (!confirm(`确定要删除调度链 "${chainId}" 吗？`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/scheduler/jobs/${chainId}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (data.code === 200) {
            showMessage('调度链已删除', 'success');
            loadChains();
            loadJobs();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    }
}

// 格式化日期时间
function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 显示消息
function showMessage(message, type = 'info') {
    // 创建消息元素
    const msgEl = document.createElement('div');
    msgEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    if (type === 'success') {
        msgEl.style.background = '#4caf50';
    } else if (type === 'error') {
        msgEl.style.background = '#f44336';
    } else {
        msgEl.style.background = '#667eea';
    }
    
    msgEl.textContent = message;
    document.body.appendChild(msgEl);
    
    // 3秒后移除
    setTimeout(() => {
        msgEl.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => msgEl.remove(), 300);
    }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);
