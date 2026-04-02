/**
 * GS2026 Dashboard2 - Core Framework
 * 应用入口和全局管理
 */

class GS2026App {
    constructor() {
        this.managers = new Map();
        this.components = new Map();
        this.config = {};
        this.initialized = false;
    }

    // 初始化应用
    async init(config = {}) {
        if (this.initialized) return;

        this.config = { ...this.getDefaultConfig(), ...config };

        // 初始化核心模块
        this.logger = new Logger(this.config.logger);
        this.eventBus = new EventBus();
        this.api = new ApiClient(this.config.api);
        this.store = new StateStore();
        this.utils = new Utils();

        // 初始化通知系统
        this.notify = new NotificationSystem();

        this.initialized = true;
        this.logger.info('GS2026 Dashboard2 initialized');
        this.emit('app:initialized');
    }

    // 注册管理器
    registerManager(manager) {
        this.managers.set(manager.name, manager);
        this.logger.debug(`Manager registered: ${manager.name}`);
    }

    // 获取管理器
    getManager(name) {
        return this.managers.get(name);
    }

    // 注册组件
    registerComponent(name, component) {
        this.components.set(name, component);
    }

    // 获取组件
    getComponent(name) {
        return this.components.get(name);
    }

    // 全局事件
    on(event, callback) {
        return this.eventBus.on(event, callback);
    }

    off(event, callback) {
        return this.eventBus.off(event, callback);
    }

    emit(event, data) {
        return this.eventBus.emit(event, data);
    }

    // 注册页面
    registerPage(name, pageClass) {
        this.pages[name] = pageClass;
        this.logger.debug(`Page registered: ${name}`);
    }

    // 初始化页面
    initPage(name) {
        const PageClass = this.pages[name];
        if (PageClass) {
            const page = new PageClass();
            if (page.init) {
                page.init();
            }
            this.currentPage = page;
            return page;
        } else {
            this.logger.error(`Page not found: ${name}`);
        }
    }

    // 默认配置
    getDefaultConfig() {
        return {
            api: {
                baseUrl: '/api',
                timeout: 30000,
                retryCount: 3
            },
            logger: {
                level: 'info',
                enableConsole: true
            }
        };
    }
}

// 全局实例
const GS2026 = new GS2026App();

// 初始化命名空间（供组件和模块注册使用）
GS2026.modules = GS2026.modules || {};
GS2026.components = GS2026.components || {};
GS2026.pages = GS2026.pages || {};

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    GS2026.init();
});
