/**
 * TabNav - Tab导航组件
 */

class TabNav extends BaseComponent {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.tabs = options.tabs || [];
        this.currentTab = options.defaultTab || this.tabs[0]?.id;
    }

    renderTemplate() {
        const buttons = this.tabs.map(tab => {
            const isActive = tab.id === this.currentTab;
            return `
                <button class="tab-btn ${isActive ? 'active' : ''}" data-tab="${tab.id}">
                    <span class="tab-icon">${tab.icon}</span>
                    <span class="tab-name">${tab.name}</span>
                </button>
            `;
        }).join('');

        return `<div class="tab-nav">${buttons}</div>`;
    }

    bindEvents() {
        this.$$('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabId = e.currentTarget.dataset.tab;
                this.switchTab(tabId);
            });
        });
    }

    switchTab(tabId) {
        if (tabId === this.currentTab) return;

        this.currentTab = tabId;

        // 更新UI
        this.$$('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });

        // 触发事件
        this.emit('switch', tabId);
    }

    getCurrent() {
        return this.currentTab;
    }

    addTab(tab) {
        this.tabs.push(tab);
        this.render();
    }
}
