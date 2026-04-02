/**
 * 报表中心页面 - 支持本地文件系统
 */
// 确保命名空间存在
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.pages) {
    GS2026.pages = {};
}

GS2026.pages.ReportPage = class ReportPage {
    constructor() {
        this.currentType = null;
        this.currentPage = 1;
        this.pageSize = 20;
        this.reports = [];
        
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
                            </div>
                        </div>
                        
                        <!-- 报告列表 -->
                        <div class="report-list" id="report-list">
                            <div class="empty-state">
                                <div class="empty-icon">📁</div>
                                <div class="empty-text">请选择报告类型</div>
                            </div>
                        </div>
                        
                        <!-- 分页 -->
                        <div class="pagination" id="pagination" style="display: none;">
                            <button class="btn btn-prev" id="btn-prev">上一页</button>
                            <span class="page-info">第 <span id="current-page">1</span> 页</span>
                            <button class="btn btn-next" id="btn-next">下一页</button>
                        </div>
                    </div>
                </div>
                
                <!-- PDF 预览模态框 -->
                <div class="modal" id="pdf-modal" style="display: none;">
                    <div class="modal-content pdf-modal-content">
                        <div class="modal-header">
                            <h3 id="pdf-title">PDF 预览</h3>
                            <button class="btn-close" id="btn-close-modal">&times;</button>
                        </div>
                        <div class="modal-body">
                            <iframe id="pdf-viewer" class="pdf-iframe"></iframe>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    bindEvents() {
        // 刷新按钮
        document.getElementById('btn-refresh')?.addEventListener('click', () => {
            this.loadTypes();
        });
        
        // 搜索输入
        document.getElementById('search-input')?.addEventListener('input', this.debounce(() => {
            this.currentPage = 1;
            this.loadReports();
        }, 300));
        
        // 分页按钮
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
        
        // 关闭模态框
        document.getElementById('btn-close-modal')?.addEventListener('click', () => {
            this.closePDFModal();
        });
        
        // 点击模态框外部关闭
        document.getElementById('pdf-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'pdf-modal') {
                this.closePDFModal();
            }
        });
    }
    
    async loadTypes() {
        const container = document.getElementById('type-list');
        container.innerHTML = '<div class="loading">加载中...</div>';
        
        try {
            const response = await fetch('/api/reports/types');
            const result = await response.json();
            
            if (result.success) {
                this.renderTypes(result.data);
            } else {
                container.innerHTML = `<div class="error">加载失败: ${result.error}</div>`;
            }
        } catch (e) {
            console.error('加载类型失败:', e);
            container.innerHTML = '<div class="error">加载失败</div>';
        }
    }
    
    renderTypes(types) {
        const container = document.getElementById('type-list');
        
        if (types.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📁</div>
                    <div class="empty-text">未找到报告目录</div>
                    <div class="empty-hint">请确保 G:\report 目录存在</div>
                </div>
            `;
            return;
        }
        
        container.innerHTML = types.map(type => `
            <div class="type-item ${type.report_type_code === this.currentType ? 'active' : ''}" 
                 data-type="${type.report_type_code}">
                <span class="type-icon">${type.report_type_icon}</span>
                <span class="type-name">${type.report_type_name}</span>
                <span class="type-count">${type.file_count}</span>
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
            const params = new URLSearchParams({
                type: this.currentType,
                page: this.currentPage,
                pageSize: this.pageSize
            });
            
            const keyword = document.getElementById('search-input')?.value;
            if (keyword) params.append('keyword', keyword);
            
            const response = await fetch(`/api/reports/list?${params}`);
            const result = await response.json();
            
            if (result.success) {
                this.reports = result.data.report_list;
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
            const size = this.formatFileSize(report.report_file_size);
            const date = report.report_date || '未知日期';
            
            return `
                <div class="report-item" data-id="${report.report_id}">
                    <div class="report-icon">📄</div>
                    <div class="report-info">
                        <div class="report-name">${report.report_name}</div>
                        <div class="report-meta">
                            <span>📅 ${date}</span>
                            <span>${size}</span>
                        </div>
                    </div>
                    <div class="report-actions">
                        <button class="btn btn-view" data-path="${report.report_id}">查看</button>
                        <button class="btn btn-download" data-path="${report.report_id}">下载</button>
                    </div>
                </div>
            `;
        }).join('');
        
        // 绑定事件
        container.querySelectorAll('.btn-view').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.viewPDF(btn.dataset.path);
            });
        });
        
        container.querySelectorAll('.btn-download').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.downloadReport(btn.dataset.path);
            });
        });
        
        // 更新分页
        document.getElementById('current-page').textContent = data.report_page;
        pagination.style.display = 'flex';
    }
    
    viewPDF(filePath) {
        const modal = document.getElementById('pdf-modal');
        const viewer = document.getElementById('pdf-viewer');
        const title = document.getElementById('pdf-title');
        
        // 从路径中提取文件名
        const fileName = filePath.split('\\').pop().split('/').pop();
        title.textContent = fileName;
        
        // 设置 PDF 查看器 URL
        const encodedPath = encodeURIComponent(filePath);
        viewer.src = `/api/reports/file/${encodeURIComponent(fileName)}/view?path=${encodedPath}`;
        
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
    
    closePDFModal() {
        const modal = document.getElementById('pdf-modal');
        const viewer = document.getElementById('pdf-viewer');
        
        modal.style.display = 'none';
        viewer.src = '';
        document.body.style.overflow = '';
    }
    
    downloadReport(filePath) {
        const fileName = filePath.split('\\').pop().split('/').pop();
        const encodedPath = encodeURIComponent(filePath);
        const url = `/api/reports/file/${encodeURIComponent(fileName)}/download?path=${encodedPath}`;
        
        // 创建临时链接下载
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
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
