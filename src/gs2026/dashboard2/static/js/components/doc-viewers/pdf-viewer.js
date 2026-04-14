/**
 * PDF 阅读器组件
 * 使用 pdf.js
 */
// 确保命名空间存在
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.components) {
    GS2026.components = {};
}

GS2026.components.PDFViewer = class PDFViewer {
    constructor(container) {
        this.container = container;
        this.pdfDoc = null;
        this.pageNum = 1;
        this.pageCount = 0;
        this.scale = 1.0;
        this.canvas = null;
        this.ctx = null;
        this.renderTask = null;
    }
    
    async load(url) {
        this.container.innerHTML = '<div class="doc-loading">加载 PDF 中...</div>';
        
        try {
            // 动态加载 pdf.js
            if (!window.pdfjsLib) {
                await this.loadPDFJS();
            }
            
            // 设置 worker
            pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/lib/pdfjs/pdf.worker.min.js';
            
            // 加载 PDF
            const loadingTask = pdfjsLib.getDocument(url);
            this.pdfDoc = await loadingTask.promise;
            this.pageCount = this.pdfDoc.numPages;
            this.pageNum = 1;
            
            // 创建渲染容器
            this.createViewer();
            
            // 渲染第一页
            await this.renderPage(this.pageNum);
            
        } catch (error) {
            console.error('PDF 加载失败:', error);
            this.container.innerHTML = `<div class="doc-error">PDF 加载失败: ${error.message}</div>`;
        }
    }
    
    loadPDFJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/lib/pdfjs/pdf.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    createViewer() {
        this.container.innerHTML = `
            <div class="pdf-viewer">
                <div class="pdf-toolbar">
                    <button class="btn-icon" id="pdf-prev" title="上一页">◀</button>
                    <span class="pdf-page-info">
                        第 <input type="number" id="pdf-page-input" value="1" min="1" max="${this.pageCount}"> / ${this.pageCount} 页
                    </span>
                    <button class="btn-icon" id="pdf-next" title="下一页">▶</button>
                    <span class="pdf-separator"></span>
                    <button class="btn-icon" id="pdf-zoom-out" title="缩小">−</button>
                    <span class="pdf-zoom-level">100%</span>
                    <button class="btn-icon" id="pdf-zoom-in" title="放大">+</button>
                </div>
                <div class="pdf-container">
                    <canvas class="pdf-canvas"></canvas>
                </div>
            </div>
        `;
        
        this.canvas = this.container.querySelector('.pdf-canvas');
        this.ctx = this.canvas.getContext('2d');
        
        // 绑定事件
        this.container.querySelector('#pdf-prev').addEventListener('click', () => this.prevPage());
        this.container.querySelector('#pdf-next').addEventListener('click', () => this.nextPage());
        this.container.querySelector('#pdf-zoom-in').addEventListener('click', () => this.zoomIn());
        this.container.querySelector('#pdf-zoom-out').addEventListener('click', () => this.zoomOut());
        
        const pageInput = this.container.querySelector('#pdf-page-input');
        pageInput.addEventListener('change', (e) => {
            const num = parseInt(e.target.value);
            if (num >= 1 && num <= this.pageCount) {
                this.goToPage(num);
            }
        });
        
        // 键盘导航
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.prevPage();
            if (e.key === 'ArrowRight') this.nextPage();
        });
    }
    
    async renderPage(num) {
        if (this.renderTask) {
            this.renderTask.cancel();
        }
        
        try {
            const page = await this.pdfDoc.getPage(num);
            const viewport = page.getViewport({ scale: this.scale });
            
            this.canvas.height = viewport.height;
            this.canvas.width = viewport.width;
            
            const renderContext = {
                canvasContext: this.ctx,
                viewport: viewport
            };
            
            this.renderTask = page.render(renderContext);
            await this.renderTask.promise;
            
            this.pageNum = num;
            this.updatePageInfo();
            
        } catch (error) {
            if (error.name !== 'RenderingCancelledException') {
                console.error('页面渲染失败:', error);
            }
        }
    }
    
    prevPage() {
        if (this.pageNum <= 1) return;
        this.renderPage(this.pageNum - 1);
    }
    
    nextPage() {
        if (this.pageNum >= this.pageCount) return;
        this.renderPage(this.pageNum + 1);
    }
    
    goToPage(num) {
        if (num >= 1 && num <= this.pageCount) {
            this.renderPage(num);
        }
    }
    
    zoomIn() {
        this.scale = Math.min(this.scale + 0.2, 3.0);
        this.updateZoomLevel();
        this.renderPage(this.pageNum);
    }
    
    zoomOut() {
        this.scale = Math.max(this.scale - 0.2, 0.5);
        this.updateZoomLevel();
        this.renderPage(this.pageNum);
    }
    
    updatePageInfo() {
        const input = this.container.querySelector('#pdf-page-input');
        if (input) input.value = this.pageNum;
    }
    
    updateZoomLevel() {
        const level = this.container.querySelector('.pdf-zoom-level');
        if (level) level.textContent = Math.round(this.scale * 100) + '%';
    }
    
    destroy() {
        if (this.renderTask) {
            this.renderTask.cancel();
        }
        this.pdfDoc = null;
    }
};
