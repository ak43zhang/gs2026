/**
 * BaseManager - 管理器基类
 * 所有业务管理器的基类
 */

// 确保 GS2026 命名空间存在
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.modules) {
    GS2026.modules = {};
}

GS2026.modules.BaseManager = class BaseManager {
    constructor(name) {
        this.name = name;
        this.state = {};
        this.listeners = {};
        
        // 注册到全局
        if (typeof GS2026 !== 'undefined' && GS2026.registerManager) {
            GS2026.registerManager(this);
        }
    }

    // 设置状态
    setState(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;
        this.emit('stateChange', { key, value, oldValue });
    }

    // 获取状态
    getState(key, defaultValue = null) {
        return this.state.hasOwnProperty(key) ? this.state[key] : defaultValue;
    }

    // 监听事件
    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
        
        // 返回取消监听函数
        return () => this.off(event, callback);
    }

    // 取消监听
    off(event, callback) {
        if (!this.listeners[event]) return;
        const index = this.listeners[event].indexOf(callback);
        if (index > -1) {
            this.listeners[event].splice(index, 1);
        }
    }

    // 触发事件
    emit(event, data) {
        // 本地事件
        if (this.listeners[event]) {
            this.listeners[event].forEach(cb => {
                try {
                    cb(data);
                } catch (e) {
                    console.error(`[${this.name}] Event handler error:`, e);
                }
            });
        }
        
        // 全局事件
        if (typeof GS2026 !== 'undefined' && GS2026.emit) {
            GS2026.emit(`${this.name}:${event}`, data);
        }
    }

    // 日志
    log(level, message, meta = {}) {
        const fullMessage = `[${this.name}] ${message}`;
        if (typeof GS2026 !== 'undefined' && GS2026.logger) {
            switch (level) {
                case 'debug':
                    GS2026.logger.debug(fullMessage, meta);
                    break;
                case 'info':
                case 'success':  // success 映射到 info
                    GS2026.logger.info(fullMessage, meta);
                    break;
                case 'warn':
                    GS2026.logger.warn(fullMessage, meta);
                    break;
                case 'error':
                    GS2026.logger.error(fullMessage, meta);
                    break;
                default:
                    console.log(fullMessage, meta);
            }
        } else {
            // 降级到 console
            const consoleMethod = level === 'success' ? 'log' : (level === 'warn' ? 'warn' : (level === 'error' ? 'error' : 'log'));
            console[consoleMethod](fullMessage, meta);
        }
    }

    // 初始化（子类实现）
    async init() {
        this.log('info', 'Initialized');
    }

    // 销毁（子类实现）
    async destroy() {
        this.listeners = {};
        this.log('info', 'Destroyed');
    }
};
