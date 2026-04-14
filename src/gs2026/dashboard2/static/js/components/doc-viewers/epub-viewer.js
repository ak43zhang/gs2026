/**
 * EPUB 阅读器组件
 * 使用 epub.js
 */
// 确保命名空间存在
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.components) {
    GS2026.components = {};
}

GS2026.components.EPUBViewer = class EPUBViewer {
    constructor(container) {
        this.container = container;
        this.book = null;
        this.rendition = null;
        this.currentLocation = null;
    }
    
    async load(url) {
        this.container.innerHTML = '<div class="doc-loading">加载 EPUB 中...</div>';
        
        try {
            // 动态加载 epub.js
            if (!window.ePub) {
                await this.loadEPUBJS();
            }
            
            // 创建阅读器容器
            this.createViewer();
            
            // 加载 EPUB
            this.book = ePub(url);
            
            // 渲染
            this.rendition = this.book.renderTo(this.container.querySelector('.epub-viewport'), {
                width: '100%',
                height: '100%',
                flow: 'paginated',
                spread: 'auto'
            });
            
            // 显示内容
            await this.rendition.display();
            
            // 绑定事件
            this.bindEvents();
            
            // 生成目录
            await this.generateToc();
            
        } catch (error) {
            console.error('EPUB 加载失败:', error);
            this.container.innerHTML = `<div class="doc-error">EPUB 加载失败: ${error.message}</div>`;
        }
    }
    
    loadEPUBJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/lib/epubjs/epub.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    createViewer() {
        this.container.innerHTML = `
            <div class="epub-viewer">
                <div class="epub-toolbar">
                    <button class="btn-icon" id="epub-prev" title="上一页">◀</button>
                    <span class="epub-location" id="epub-location">加载中...</span>
                    <button class="btn-icon" id="epub-next" title="下一页">▶</button>
                    <span class="epub-separator"></span>
                    <button class="btn-icon" id="epub-toc" title="目录">📑</button>
                    <button class="btn-icon" id="epub-bookmark" title="书签">🔖</button>
                </div>
                <div class="epub-container">
                    <div class="epub-sidebar" id="epub-sidebar" style="display: none;">
                        <div class="epub-toc" id="epub-toc-list"></div>
                    </div>
                    <div class="epub-viewport"></div>
                </div>
            </div>
        `;
    }
    
    bindEvents() {
        // 翻页按钮
        this.container.querySelector('#epub-prev').addEventListener('click', () => this.prevPage());
        this.container.querySelector('#epub-next').addEventListener('click', () => this.nextPage());
        
        // 目录按钮
        this.container.querySelector('#epub-toc').addEventListener('click', () => this.toggleToc());
        
        // 位置变化事件
        this.rendition.on('relocated', (location) => {
            this.currentLocation = location;
            this.updateLocationInfo();
        });
        
        // 键盘导航
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.prevPage();
            if (e.key === 'ArrowRight') this.nextPage();
        });
    }
    
    async generateToc() {
        try {
            const navigation = await this.book.navigation;
            const tocList = this.container.querySelector('#epub-toc-list');
            
            if (navigation && navigation.toc) {
                tocList.innerHTML = this.renderTocItems(navigation.toc);
                
                // 绑定目录点击事件
                tocList.querySelectorAll('.toc-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const href = item.dataset.href;
                        this.rendition.display(href);
                        this.hideToc();
                    });
                });
            }
        } catch (error) {
            console.error('生成目录失败:', error);
        }
    }
    
    renderTocItems(items, level = 0) {
        return items.map(item => `
            <div class="toc-item" data-href="${item.href}" style="padding-left: ${level * 20}px">
                ${item.label}
            </div>
            ${item.subitems ? this.renderTocItems(item.subitems, level + 1) : ''}
        `).join('');
    }
    
    prevPage() {
        this.rendition.prev();
    }
    
    nextPage() {
        this.rendition.next();
    }
    
    toggleToc() {
        const sidebar = this.container.querySelector('#epub-sidebar');
        sidebar.style.display = sidebar.style.display === 'none' ? 'block' : 'none';
    }
    
    hideToc() {
        const sidebar = this.container.querySelector('#epub-sidebar');
        sidebar.style.display = 'none';
    }
    
    updateLocationInfo() {
        if (!this.currentLocation) return;
        
        const location = this.container.querySelector('#epub-location');
        if (location) {
            const current = this.currentLocation.start.displayed.page;
            const total = this.currentLocation.start.displayed.total;
            location.textContent = `第 ${current} / ${total} 页`;
        }
    }
    
    // 获取当前位置（用于语音同步）
    getCurrentLocation() {
        return this.currentLocation;
    }
    
    // 跳转到指定位置
    goToLocation(cfi) {
        this.rendition.display(cfi);
    }
    
    destroy() {
        if (this.rendition) {
            this.rendition.destroy();
        }
        if (this.book) {
            this.book.destroy();
        }
    }
};
