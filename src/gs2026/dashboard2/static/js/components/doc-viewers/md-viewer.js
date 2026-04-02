/**
 * Markdown 阅读器组件
 * 使用 marked.js
 */
GS2026.components.MarkdownViewer = class MarkdownViewer {
    constructor(container) {
        this.container = container;
    }
    
    async load(content) {
        this.container.innerHTML = '<div class="doc-loading">加载中...</div>';
        
        try {
            // 动态加载 marked.js
            if (!window.marked) {
                await this.loadMarkedJS();
            }
            
            // 配置 marked
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: true,
                mangle: false,
                sanitize: false,
                smartLists: true,
                smartypants: true,
                xhtml: false
            });
            
            // 渲染 Markdown
            const html = marked.parse(content);
            
            // 创建阅读器
            this.createViewer(html);
            
            // 代码高亮
            this.highlightCode();
            
        } catch (error) {
            console.error('Markdown 渲染失败:', error);
            this.container.innerHTML = `<div class="doc-error">渲染失败: ${error.message}</div>`;
        }
    }
    
    loadMarkedJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/lib/marked/marked.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    createViewer(html) {
        this.container.innerHTML = `
            <div class="md-viewer">
                <div class="md-toolbar">
                    <button class="btn-icon" id="md-toc" title="目录">📑</button>
                </div>
                <div class="md-container">
                    <div class="md-sidebar" id="md-sidebar" style="display: none;">
                        <div class="md-toc" id="md-toc-list"></div>
                    </div>
                    <div class="md-content markdown-body">
                        ${html}
                    </div>
                </div>
            </div>
        `;
        
        // 生成目录
        this.generateToc();
        
        // 绑定事件
        this.container.querySelector('#md-toc').addEventListener('click', () => this.toggleToc());
    }
    
    generateToc() {
        const content = this.container.querySelector('.md-content');
        const headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6');
        const tocList = this.container.querySelector('#md-toc-list');
        
        if (headings.length === 0) {
            tocList.innerHTML = '<div class="toc-empty">无目录</div>';
            return;
        }
        
        // 为标题添加 ID
        headings.forEach((heading, index) => {
            if (!heading.id) {
                heading.id = `heading-${index}`;
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
        const sidebar = this.container.querySelector('#md-sidebar');
        sidebar.style.display = sidebar.style.display === 'none' ? 'block' : 'none';
    }
    
    hideToc() {
        const sidebar = this.container.querySelector('#md-sidebar');
        sidebar.style.display = 'none';
    }
    
    async highlightCode() {
        // 如果页面有 highlight.js，使用它
        if (window.hljs) {
            this.container.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }
    }
    
    // 获取纯文本内容（用于语音播报）
    getTextContent() {
        const content = this.container.querySelector('.md-content');
        return content ? content.textContent : '';
    }
    
    destroy() {
        // 无需清理
    }
};
