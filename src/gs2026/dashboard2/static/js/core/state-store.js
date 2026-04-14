/**
 * StateStore - 状态管理
 * 简单的全局状态管理，支持订阅和持久化
 */

class StateStore {
    constructor() {
        this.state = new Map();
        this.subscribers = new Map();
        this.persistKeys = new Set();
    }

    // 设置状态
    set(key, value, persist = false) {
        const oldValue = this.state.get(key);
        this.state.set(key, value);

        if (persist) {
            this.persistKeys.add(key);
            this.saveToStorage(key, value);
        }

        // 通知订阅者
        this.notify(key, value, oldValue);
    }

    // 获取状态
    get(key, defaultValue = null) {
        return this.state.has(key) ? this.state.get(key) : defaultValue;
    }

    // 删除状态
    delete(key) {
        this.state.delete(key);
        this.subscribers.delete(key);
        this.persistKeys.delete(key);
        localStorage.removeItem(`gs2026:${key}`);
    }

    // 订阅状态变化
    subscribe(key, callback) {
        if (!this.subscribers.has(key)) {
            this.subscribers.set(key, []);
        }
        this.subscribers.get(key).push(callback);

        // 立即返回当前值
        if (this.state.has(key)) {
            callback(this.state.get(key), null);
        }

        // 返回取消订阅函数
        return () => this.unsubscribe(key, callback);
    }

    // 取消订阅
    unsubscribe(key, callback) {
        if (!this.subscribers.has(key)) return;
        const callbacks = this.subscribers.get(key);
        const index = callbacks.indexOf(callback);
        if (index > -1) {
            callbacks.splice(index, 1);
        }
    }

    // 通知订阅者
    notify(key, newValue, oldValue) {
        if (!this.subscribers.has(key)) return;
        this.subscribers.get(key).forEach(callback => {
            try {
                callback(newValue, oldValue);
            } catch (e) {
                console.error(`State subscriber error for ${key}:`, e);
            }
        });
    }

    // 持久化到 localStorage
    saveToStorage(key, value) {
        try {
            localStorage.setItem(`gs2026:${key}`, JSON.stringify(value));
        } catch (e) {
            console.warn('Failed to save to localStorage:', e);
        }
    }

    // 从 localStorage 恢复
    loadFromStorage(key) {
        try {
            const value = localStorage.getItem(`gs2026:${key}`);
            return value ? JSON.parse(value) : null;
        } catch (e) {
            console.warn('Failed to load from localStorage:', e);
            return null;
        }
    }

    // 批量恢复持久化状态
    restorePersisted() {
        for (const key of this.persistKeys) {
            const value = this.loadFromStorage(key);
            if (value !== null) {
                this.state.set(key, value);
            }
        }
    }

    // 清空所有状态
    clear() {
        this.state.clear();
        this.subscribers.clear();
        this.persistKeys.clear();
    }
}
