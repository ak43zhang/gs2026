/**
 * BaseComponent - 组件基类
 * 所有UI组件的基类
 */

class BaseComponent {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.options = options;
        this.eventListeners = [];
        this.children = [];
        
        if (!this.container && !options.lazy) {
            console.warn(`[${this.constructor.name}] Container #${containerId} not found`);
        }
    }

    // 渲染模板（子类实现）
    renderTemplate(data) {
        return '';
    }

    // 渲染
    render(data = {}) {
        if (!this.container) {
            this.container = document.getElementById(this.containerId);
            if (!this.container) {
                console.warn(`[${this.constructor.name}] Container #${this.containerId} not found`);
                return false;
            }
        }

        try {
            const html = this.renderTemplate(data);
            this.container.innerHTML = html;
            this.bindEvents();
            this.onRender();
            return true;
        } catch (e) {
            console.error(`[${this.constructor.name}] Render error:`, e);
            return false;
        }
    }

    // 绑定事件（子类实现）
    bindEvents() {}

    // 渲染后回调（子类实现）
    onRender() {}

    // 安全获取元素
    $(selector) {
        return this.container?.querySelector(selector);
    }

    $$(selector) {
        return this.container?.querySelectorAll(selector) || [];
    }

    // 绑定事件（带自动清理）
    on(element, event, handler, options = {}) {
        if (typeof element === 'string') {
            element = this.$(element);
        }
        if (!element) return;

        element.addEventListener(event, handler, options);
        this.eventListeners.push({ element, event, handler });
    }

    // 触发组件事件
    emit(eventName, data) {
        // 本地监听
        if (this.options.on && this.options.on[eventName]) {
            this.options.on[eventName](data);
        }
        
        // 全局事件
        if (typeof GS2026 !== 'undefined') {
            GS2026.emit(`${this.constructor.name}:${eventName}`, data);
        }
    }

    // 添加子组件
    addChild(child) {
        this.children.push(child);
    }

    // 显示
    show() {
        if (this.container) {
            this.container.style.display = '';
        }
    }

    // 隐藏
    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    }

    // 销毁
    destroy() {
        // 清理事件监听
        this.eventListeners.forEach(({ element, event, handler }) => {
            element.removeEventListener(event, handler);
        });
        this.eventListeners = [];

        // 销毁子组件
        this.children.forEach(child => child.destroy());
        this.children = [];

        // 清空容器
        if (this.container) {
            this.container.innerHTML = '';
        }
    }
}
