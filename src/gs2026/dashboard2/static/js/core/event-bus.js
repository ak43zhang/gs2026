/**
 * EventBus - 事件总线
 * 发布订阅模式，支持命名空间
 */

class EventBus {
    constructor() {
        this.events = new Map();
        this.onceEvents = new Map();
    }

    // 订阅事件
    on(event, callback) {
        if (!this.events.has(event)) {
            this.events.set(event, []);
        }
        this.events.get(event).push(callback);

        // 返回取消订阅函数
        return () => this.off(event, callback);
    }

    // 一次性订阅
    once(event, callback) {
        const wrapper = (data) => {
            this.off(event, wrapper);
            callback(data);
        };
        return this.on(event, wrapper);
    }

    // 取消订阅
    off(event, callback) {
        if (!this.events.has(event)) return;

        const callbacks = this.events.get(event);
        const index = callbacks.indexOf(callback);
        if (index > -1) {
            callbacks.splice(index, 1);
        }

        if (callbacks.length === 0) {
            this.events.delete(event);
        }
    }

    // 发布事件
    emit(event, data) {
        if (!this.events.has(event)) return;

        const callbacks = this.events.get(event);
        callbacks.forEach(callback => {
            try {
                callback(data);
            } catch (e) {
                console.error(`Event handler error for ${event}:`, e);
            }
        });
    }

    // 清空所有事件
    clear() {
        this.events.clear();
    }
}
