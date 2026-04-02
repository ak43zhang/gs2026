/**
 * Excel 阅读器组件
 * 使用 SheetJS (xlsx.js)
 */
GS2026.components.XlsxViewer = class XlsxViewer {
    constructor(container) {
        this.container = container;
        this.workbook = null;
        this.currentSheet = 0;
    }
    
    async load(arrayBuffer) {
        this.container.innerHTML = '<div class="doc-loading">加载 Excel 中...</div>';
        
        try {
            // 动态加载 SheetJS
            if (!window.XLSX) {
                await this.loadSheetJS();
            }
            
            // 读取 Excel
            this.workbook = XLSX.read(arrayBuffer, { type: 'array' });
            
            // 创建阅读器
            this.createViewer();
            
            // 渲染第一个工作表
            this.renderSheet(0);
            
        } catch (error) {
            console.error('Excel 加载失败:', error);
            this.container.innerHTML = `<div class="doc-error">Excel 加载失败: ${error.message}</div>`;
        }
    }
    
    loadSheetJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/lib/sheetjs/xlsx.full.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    createViewer() {
        const sheetNames = this.workbook.SheetNames;
        
        this.container.innerHTML = `
            <div class="xlsx-viewer">
                <div class="xlsx-toolbar">
                    <span class="xlsx-sheets">
                        ${sheetNames.map((name, index) => `
                            <button class="btn-sheet ${index === 0 ? 'active' : ''}" 
                                    data-index="${index}">${name}</button>
                        `).join('')}
                    </span>
                </div>
                <div class="xlsx-container">
                    <div class="xlsx-content" id="xlsx-content"></div>
                </div>
            </div>
        `;
        
        // 绑定工作表切换事件
        this.container.querySelectorAll('.btn-sheet').forEach(btn => {
            btn.addEventListener('click', () => {
                const index = parseInt(btn.dataset.index);
                this.renderSheet(index);
                
                // 更新选中状态
                this.container.querySelectorAll('.btn-sheet').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }
    
    renderSheet(index) {
        const sheetName = this.workbook.SheetNames[index];
        const worksheet = this.workbook.Sheets[sheetName];
        
        // 转换为 JSON
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
        
        if (jsonData.length === 0) {
            document.getElementById('xlsx-content').innerHTML = '<div class="empty">空工作表</div>';
            return;
        }
        
        // 渲染表格
        const html = this.renderTable(jsonData);
        document.getElementById('xlsx-content').innerHTML = html;
        
        this.currentSheet = index;
    }
    
    renderTable(data) {
        if (!data || data.length === 0) return '<div class="empty">无数据</div>';
        
        const maxCols = Math.max(...data.map(row => row.length));
        
        let html = '<table class="xlsx-table"><thead><tr>';
        
        // 表头（第一行）
        const headerRow = data[0] || [];
        for (let i = 0; i < maxCols; i++) {
            html += `<th>${this.escapeHtml(headerRow[i] || '')}</th>`;
        }
        html += '</tr></thead><tbody>';
        
        // 数据行
        for (let i = 1; i < data.length; i++) {
            html += '<tr>';
            const row = data[i] || [];
            for (let j = 0; j < maxCols; j++) {
                const cell = row[j];
                const value = cell !== undefined && cell !== null ? String(cell) : '';
                html += `<td>${this.escapeHtml(value)}</td>`;
            }
            html += '</tr>';
        }
        
        html += '</tbody></table>';
        return html;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // 获取纯文本内容（用于语音播报 - 仅摘要）
    getTextContent() {
        if (!this.workbook) return '';
        
        const sheetName = this.workbook.SheetNames[this.currentSheet];
        const worksheet = this.workbook.Sheets[sheetName];
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
        
        // 提取前 10 行作为摘要
        const summary = jsonData.slice(0, 10).map(row => row.join(' ')).join('\n');
        return `Excel 表格《${sheetName}》，共 ${jsonData.length} 行数据。前10行摘要：\n${summary}`;
    }
    
    destroy() {
        this.workbook = null;
    }
};
