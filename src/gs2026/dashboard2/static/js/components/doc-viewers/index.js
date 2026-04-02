/**
 * 文档阅读器工厂
 */
// 确保命名空间存在
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.components) {
    GS2026.components = {};
}

GS2026.components.DocViewerFactory = {
    createViewer(format, container) {
        switch(format.toLowerCase()) {
            case 'pdf':
                return new GS2026.components.PDFViewer(container);
            case 'epub':
                return new GS2026.components.EPUBViewer(container);
            case 'docx':
                return new GS2026.components.DocxViewer(container);
            case 'xlsx':
                return new GS2026.components.XlsxViewer(container);
            case 'md':
            case 'markdown':
                return new GS2026.components.MarkdownViewer(container);
            case 'txt':
            case 'text':
                return new GS2026.components.TextViewer(container);
            case 'html':
            case 'htm':
                return new GS2026.components.HTMLViewer(container);
            default:
                return new GS2026.components.DefaultViewer(container);
        }
    }
};

/**
 * 文本阅读器
 */
GS2026.components.TextViewer = class TextViewer {
    constructor(container) {
        this.container = container;
    }
    
    load(content) {
        this.container.innerHTML = `
            <div class="text-viewer">
                <pre class="text-content">${this.escapeHtml(content)}</pre>
            </div>
        `;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    getTextContent() {
        const content = this.container.querySelector('.text-content');
        return content ? content.textContent : '';
    }
    
    destroy() {}
};

/**
 * HTML 阅读器
 */
GS2026.components.HTMLViewer = class HTMLViewer {
    constructor(container) {
        this.container = container;
    }
    
    load(content) {
        this.container.innerHTML = `
            <div class="html-viewer">
                <iframe class="html-iframe" sandbox="allow-same-origin"></iframe>
            </div>
        `;
        
        const iframe = this.container.querySelector('.html-iframe');
        iframe.srcdoc = content;
    }
    
    getTextContent() {
        const iframe = this.container.querySelector('.html-iframe');
        return iframe ? iframe.contentDocument.body.textContent : '';
    }
    
    destroy() {}
};

/**
 * 默认阅读器（不支持预览）
 */
GS2026.components.DefaultViewer = class DefaultViewer {
    constructor(container) {
        this.container = container;
    }
    
    load() {
        this.container.innerHTML = `
            <div class="unsupported-viewer">
                <div class="unsupported-icon">📄</div>
                <div class="unsupported-text">该格式暂不支持在线预览</div>
            </div>
        `;
    }
    
    getTextContent() {
        return '';
    }
    
    destroy() {}
};
