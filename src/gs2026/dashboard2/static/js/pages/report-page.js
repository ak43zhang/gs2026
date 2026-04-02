/**
 * 报表中心页面
 */
GS2026.pages.ReportPage = class ReportPage {
    constructor() {
        this.collectionManager = new GS2026.modules.ReportManager();
        this.currentType = null;
        this.currentPage = 1;
        this.pageSize = 20;
        
        this.init();
    }
    
    init() {
        this.render();
        this.bindEvents();
        this.loadTypes();
    }
    
    render() {
        const container = document.getElementById('main-content');
        if (!container) return;
        
        container.innerHTML = `
            <div class="report-page">
                <div class="report-header">
                    <h1>📊 报表中心</h1>
                    <button class="btn btn-refresh" id="btn-refresh">
                        <span>🔄</span> 刷新
                    </button>
                </div>
                
                <div class="report-container">
                    <!-- 左侧类型导航 -->
                    <div class="report-sidebar">
                        <div class="type-list" id="type-list">
                            <div class="loading">加载中...</div>
                        </div>
                    </div>
                    
                    <!-- 右侧内容区 -->
                    <div class="report-content">
                        <!-- 筛选栏 -->
                        <div class="filter-bar">
                            <div class="filter-left">
                                <h2 id="current-type-name">请选择报告类型</h2>
                            </div>
                            <div class="filter-right">
                                <input type="text" id="search-input" placeholder="🔍 搜索报告..." class="search-input">
                                <input type="date" id="start-date" class="date-input">
                                <span>至</span>
                                <input type="date" id="end-date" class="date-input">
                                <select id="format-filter" class="format-select">
                                    <option value="">所有格式</option>
                                    <option value="pdf">PDF</option>
                                    <option value="epub">EPUB</option>
                                    <option value="docx">Word</option>
                                    <option value="xlsx">Excel</option>
                                    <option value="md">Markdown</option>
                                </select>
                                <button class="btn btn-generate" id="btn-generate">
                                    <span>➕</span> 生成报告
                                </button>
                            </div>
                        </div>
                        
                        <!-- 报告列表 -->
                        <div class="report-list" id="report-list">
                            <div class="empty-state">
                                <div class="empty-icon">📊</div>
                                <div class="empty-text">请选择左侧报告类型</div>
                            </div>
                        </div>
                        
                        <!-- 分页 -->
                        <div class="pagination" id="pagination" style="display: none;">
                            <button class="btn-page" id="btn-prev">上一页</button>
                            <span class="page-info">第 <span id="current-page">1</span> 页</span>
                            <button class="btn-page" id="btn-next">下一页</button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 文档阅读器弹窗 -->
            <div class="report-viewer-modal" id="viewer-modal" style="display: none;">
                <div class="viewer-overlay"></div>
                <div class="viewer-container">
                    <div class="viewer-header">
                        <h3 id="viewer-title">报告标题</h3>
                        <div class="viewer-actions">
                            <button class="btn-icon" id="btn-tts" title="语音播报">🔊</button>
                            <button class="btn-icon" id="btn-close" title="关闭">✕</button>
                        </div>
                    </div>
                    <div class="viewer-body" id="viewer-body">
                        <!-- 文档内容 -->
                    </div>
                    <div class="viewer-footer" id="viewer-footer">
                        <!-- 播放控制条 -->
                    </div>
                </div>
            </div>
        `;
    }
    
    bindEvents() {
        // 刷新按钮
        document.getElementById('btn-refresh')?.addEventListener('click', () => {
            this.loadTypes();
            if (this.currentType) {
                this.loadReports();
            }
        });
        
        // 搜索
        document.getElementById('search-input')?.addEventListener('input', this.debounce(() => {
            this.currentPage = 1;
            this.loadReports();
        }, 500));
        
        // 日期筛选
        document.getElementById('start-date')?.addEventListener('change', () => {
            this.currentPage = 1;
            this.loadReports();
        });
        document.getElementById('end-date')?.addEventListener('change', () => {
            this.currentPage = 1;
            this.loadReports();
        });
        
        // 格式筛选
        document.getElementById('format-filter')?.addEventListener('change', () => {
            this.currentPage = 1;
            this.loadReports();
        });
        
        // 生成报告
        document.getElementById('btn-generate')?.addEventListener('click', () => {
            this.showGenerateDialog();
        });
        
        // 分页
        document.getElementById('btn-prev')?.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadReports();
            }
        });
        document.getElementById('btn-next')?.addEventListener('click', () => {
            this.currentPage++;
            this.loadReports();
        });
        
        // 关闭阅读器
        document.getElementById('btn-close')?.addEventListener('click', () => {
            this.closeViewer();
        });
        document.querySelector('.viewer-overlay')?.addEventListener('click', () => {
            this.closeViewer();
        });
        
        // 语音播报
        document.getElementById('btn-tts')?.addEventListener('click', () => {
            this.toggleTTS();
        });
    }
    
    async loadTypes() {
        try {
            const result = await this.collectionManager.getReportTypes();
            if (result.success) {
                this.renderTypes(result.data);
            }
        } catch (e) {
            console.error('加载报告类型失败:', e);
        }
    }
    
    renderTypes(types) {
        const container = document.getElementById('type-list');
        if (!container) return;
        
        if (!types || types.length === 0) {
            container.innerHTML = '<div class="empty">暂无报告类型</div>';
            return;
        }
        
        container.innerHTML = types.map(type => `
            <div class="type-item ${type.report_type_code === this.currentType ? 'active' : ''}" 
                 data-type="${type.report_type_code}">
                <span class="type-icon">${type.report_type_icon}</span>
                <span class="type-name">${type.report_type_name}</span>
                <span class="type-count">${type.report_count || 0}</span>
            </div>
        `).join('');
        
        // 绑定点击事件
        container.querySelectorAll('.type-item').forEach(item => {
            item.addEventListener('click', () => {
                const type = item.dataset.type;
                this.selectType(type);
            });
        });
    }
    
    selectType(typeCode) {
        this.currentType = typeCode;
        this.currentPage = 1;
        
        // 更新选中状态
        document.querySelectorAll('.type-item').forEach(item => {
            item.classList.toggle('active', item.dataset.type === typeCode);
        });
        
        // 更新标题
        const typeName = document.querySelector(`.type-item[data-type="${typeCode}"] .type-name`)?.textContent || typeCode;
        document.getElementById('current-type-name').textContent = typeName;
        
        // 加载报告
        this.loadReports();
    }
    
    async loadReports() {
        if (!this.currentType) return;
        
        const listContainer = document.getElementById('report-list');
        listContainer.innerHTML = '<div class="loading">加载中...</div>';
        
        try {
            const filters = {
                type: this.currentType,
                page: this.currentPage,
                pageSize: this.pageSize
            };
            
            // 添加筛选条件
            const keyword = document.getElementById('search-input')?.value;
            if (keyword) filters.keyword = keyword;
            
            const startDate = document.getElementById('start-date')?.value;
            if (startDate) filters.startDate = startDate;
            
            const endDate = document.getElementById('end-date')?.value;
            if (endDate) filters.endDate = endDate;
            
            const format = document.getElementById('format-filter')?.value;
            if (format) filters.format = format;
            
            const result = await this.collectionManager.listReports(filters);
            
            if (result.success) {
                this.renderReports(result.data);
            } else {
                listContainer.innerHTML = `<div class="error">加载失败: ${result.error}</div>`;
            }
        } catch (e) {
            console.error('加载报告失败:', e);
            listContainer.innerHTML = '<div class="error">加载失败</div>';
        }
    }
    
    renderReports(data) {
        const container = document.getElementById('report-list');
        const pagination = document.getElementById('pagination');
        
        if (!data.report_list || data.report_list.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📄</div>
                    <div class="empty-text">暂无报告</div>
                </div>
            `;
            pagination.style.display = 'none';
            return;
        }
        
        // 渲染列表
        container.innerHTML = data.report_list.map(report => {
            const formatIcons = {
                'pdf': '📄', 'epub': '📚', 'docx': '📝',
                'xlsx': '📊', 'md': '📃', 'html': '🌐', 'txt': '📋'
            };
            const icon = formatIcons[report.report_file_format] || '📄';
            const size = this.formatFileSize(report.report_file_size);
            const ttsStatus = report.report_tts_status === 'completed' ? '🔊' : '';
            const ttsDuration = report.report_tts_duration ? this.formatDuration(report.report_tts_duration) : '';
            
            return `
                <div class="report-item" data-id="${report.report_id}">
                    <div class="report-icon">${icon}</div>
                    <div class="report-info">
                        <div class="report-name">${report.report_name}</div>
                        <div class="report-meta">
                            <span>📅 ${report.report_date}</span>
                            <span>${report.report_page_count || 0} 页</span>
                            <span>${size}</span>
                        </div>
                    </div>
                    <div class="report-actions">
                        ${ttsStatus ? `<span class="tts-badge" title="语音就绪">🔊 ${ttsDuration}</span>` : ''}
                        <button class="btn btn-view" data-id="${report.report_id}">查看</button>
                        ${report.report_tts_status !== 'completed' ? 
                            `<button class="btn btn-tts-generate" data-id="${report.report_id}">生成语音</button>` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        // 绑定事件
        container.querySelectorAll('.btn-view').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.viewReport(btn.dataset.id);
            });
        });
        
        container.querySelectorAll('.btn-tts-generate').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.generateTTS(btn.dataset.id);
            });
        });
        
        // 更新分页
        document.getElementById('current-page').textContent = data.report_page;
        pagination.style.display = 'flex';
    }
    
    async viewReport(reportId) {
        try {
            const result = await this.collectionManager.getReport(reportId);
            if (result.success) {
                this.openViewer(result.data);
            }
        } catch (e) {
            console.error('查看报告失败:', e);
        }
    }
    
    openViewer(report) {
        const modal = document.getElementById('viewer-modal');
        const title = document.getElementById('viewer-title');
        const body = document.getElementById('viewer-body');
        
        title.textContent = report.report_name;
        body.innerHTML = '<div class="loading">加载中...</div>';
        modal.style.display = 'block';
        
        // 加载文档内容
        this.loadDocumentContent(report);
    }
    
    async loadDocumentContent(report) {
        const body = document.getElementById('viewer-body');
        const format = report.report_file_format;
        
        try {
            if (format === 'pdf' || format === 'epub') {
                // 使用 iframe 或专用阅读器
                body.innerHTML = `
                    <iframe src="${report.report_view_url}" 
                            class="doc-iframe" 
                            frameborder="0">
                    </iframe>
                `;
            } else if (format === 'md' || format === 'html') {
                const response = await fetch(report.report_view_url);
                const data = await response.json();
                if (data.success) {
                    body.innerHTML = `<div class="doc-content">${data.content}</div>`;
                }
            } else {
                body.innerHTML = '<div class="unsupported">该格式暂不支持在线预览</div>';
            }
        } catch (e) {
            body.innerHTML = '<div class="error">加载失败</div>';
        }
    }
    
    closeViewer() {
        const modal = document.getElementById('viewer-modal');
        modal.style.display = 'none';
        // 停止语音播放
        this.stopTTS();
    }
    
    async generateTTS(reportId) {
        try {
            const result = await this.collectionManager.generateTTS(reportId);
            if (result.success) {
                alert('语音生成任务已启动');
                // 轮询状态
                this.pollTTSStatus(reportId);
            }
        } catch (e) {
            console.error('生成语音失败:', e);
        }
    }
    
    async pollTTSStatus(reportId) {
        const checkStatus = async () => {
            try {
                const result = await this.collectionManager.getTTSStatus(reportId);
                if (result.success) {
                    if (result.data.report_tts_status === 'completed') {
                        this.loadReports(); // 刷新列表
                        return;
                    } else if (result.data.report_tts_status === 'failed') {
                        return;
                    }
                    setTimeout(checkStatus, 3000);
                }
            } catch (e) {
                console.error('查询语音状态失败:', e);
            }
        };
        checkStatus();
    }
    
    toggleTTS() {
        // TODO: 实现语音播放控制
        console.log('Toggle TTS');
    }
    
    stopTTS() {
        // TODO: 停止语音播放
    }
    
    showGenerateDialog() {
        // TODO: 显示生成报告对话框
        alert('生成报告功能开发中...');
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
    
    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    debounce(fn, delay) {
        let timer = null;
        return function(...args) {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }
};

// 注册页面
GS2026.registerPage('report', GS2026.pages.ReportPage);
