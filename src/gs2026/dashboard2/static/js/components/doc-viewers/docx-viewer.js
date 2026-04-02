/**
 * Word 阅读器组件
 * 使用 mammoth.js 转换为 HTML
 */
GS2026.components.DocxViewer = class DocxViewer {
    constructor(container) {
        this.container = container;
    }
    
    async load(arrayBuffer) {
        this.container.innerHTML = '<div class="doc-loading">加载 Word 文档中...</div>';
        
        try {
            // 动态加载 mammoth.js
            if (!window.mammoth) {
                await this.loadMammothJS();
            }
            
            // 转换 Word 为 HTML
            const result = await mammoth.convertToHtml({ arrayBuffer: arrayBuffer }, {
                styleMap: [
                    "p[style-name='Heading 1'] => h1",
                    "p[style-name='Heading 2'] => h2",
                    "p[style-name='Heading 3'] => h3",
                    "p[style-name='Heading 4'] => h4",
                    "p[style-name='Heading 5'] => h5",
                    "p[style-name='Heading 6'] => h6"
                ]
            });
            
            if (result.messages.length > 0) {
                console.log('Word 转换消息:', result.messages);
            }
            
            // 创建阅读器
            this.createViewer(result.value);
            
            // 生成目录
            this.generateToc();
            
        } catch (error) {
            console.error('Word 文档加载失败:', error);
            this.container.innerHTML = `<div class="doc-error">Word 文档加载失败: ${error.message}</div>`;
        }
    }
    
    loadMammothJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/lib/mammoth/mammoth.browser.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    createViewer(html) {
        this.container.innerHTML = `
            <div class="docx-viewer">
                <div class="docx-toolbar">
                    <button class="btn-icon" id="docx-toc" title="目录">📑</button>
                </div>
                <div class="docx-container">
                    <div class="docx-sidebar" id="docx-sidebar" style="display: none;">
                        <div class="docx-toc" id="docx-toc-list"></div>
                    </div>
                    <div class="docx-content">
                        ${html}
                    </div>
                </div>
            </div>
        `;
        
        // 绑定事件
        this.container.querySelector('#docx-toc').addEventListener('click', () => this.toggleToc());
    }
    
    generateToc() {
        const content = this.container.querySelector('.docx-content');
        const headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6');
        const tocList = this.container.querySelector('#docx-toc-list');
        
        if (headings.length === 0) {
            tocList.innerHTML = '<div class="toc-empty">无目录</div>';
            return;
        }
        
        // 为标题添加 ID
        headings.forEach((heading, index) => {
            if (!heading.id) {
                heading.id = `docx-heading-${index}`;
            }
        });
        
        // 生成目录 HTML
        tocList.innerHTML = Array.from(headings).map(heading => {
            const level = parseInt(heading.tagName[1]);
            const padding = (level - 1) * 15;
            return `
                <div class="toc-item" data-target="${heading.id}" style="padding-left: ${padding}px">
                    ${heading.textContent}
                </div>
            `;
        }).join('');
        
        // 绑定点击事件
        tocList.querySelectorAll('.toc-item').forEach(item => {
            item.addEventListener('click', () => {
                const targetId = item.dataset.target;
                const target = document.getElementById(targetId);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth' });
                    this.hideToc();
                }
            });
        });
    }
    
    toggleToc() {
        const sidebar = this.container.querySelector('#docx-sidebar');
        sidebar.style.display = sidebar.style.display === 'none' ? 'block' : 'none';
    }
    
    hideToc() {
        const sidebar = this.container.querySelector('#docx-sidebar');
        sidebar.style.display = 'none';
    }
    
    // 获取纯文本内容（用于语音播报）
    getTextContent() {
        const content = this.container.querySelector('.docx-content');
        return content ? content.textContent : '';
    }
    
    destroy() {
        // 无需清理
    }
};
