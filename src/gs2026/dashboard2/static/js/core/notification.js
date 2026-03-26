/**
 * NotificationSystem - 通知系统
 * 提供浏览器通知、Toast提示等功能
 */

class NotificationSystem {
    constructor() {
        this.permission = 'default';
        this.toastContainer = null;
        this.init();
    }

    async init() {
        // 创建 Toast 容器
        this.createToastContainer();

        // 检查浏览器通知权限
        if ('Notification' in window) {
            this.permission = Notification.permission;
        }
    }

    // 创建 Toast 容器
    createToastContainer() {
        if (document.getElementById('toast-container')) return;

        this.toastContainer = document.createElement('div');
        this.toastContainer.id = 'toast-container';
        this.toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;
        document.body.appendChild(this.toastContainer);
    }

    // 显示 Toast
    showToast(message, type = 'info', duration = 3000) {
        if (!this.toastContainer) {
            this.createToastContainer();
        }

        const toast = document.createElement('div');
        const colors = {
            success: '#52c41a',
            error: '#f5222d',
            warning: '#faad14',
            info: '#1890ff'
        };
        const color = colors[type] || colors.info;

        toast.style.cssText = `
            background: ${color};
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            font-size: 14px;
            animation: slideInRight 0.3s ease-out;
            max-width: 300px;
        `;
        toast.textContent = message;

        this.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // 请求通知权限
    async requestPermission() {
        if (!('Notification' in window)) {
            console.warn('Browser does not support notifications');
            return false;
        }

        if (Notification.permission === 'granted') {
            return true;
        }

        if (Notification.permission === 'denied') {
            return false;
        }

        try {
            const permission = await Notification.requestPermission();
            this.permission = permission;
            return permission === 'granted';
        } catch (e) {
            console.error('Notification permission request failed:', e);
            return false;
        }
    }

    // 发送系统通知
    sendNotification(title, options = {}) {
        if (this.permission !== 'granted') {
            this.showToast('请先启用浏览器通知权限', 'warning');
            return;
        }

        try {
            const notification = new Notification(title, {
                icon: '/static/img/icon-192.png',
                badge: '/static/img/badge-72.png',
                ...options
            });

            notification.onclick = () => {
                window.focus();
                notification.close();
            };

            return notification;
        } catch (e) {
            console.error('Failed to send notification:', e);
        }
    }

    // 语音播报（使用 Web Speech API）
    speak(text, options = {}) {
        if (!('speechSynthesis' in window)) {
            console.warn('Browser does not support speech synthesis');
            return;
        }

        // 取消之前的播报
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = options.lang || 'zh-CN';
        utterance.rate = options.rate || 1.0;
        utterance.pitch = options.pitch || 1.0;
        utterance.volume = options.volume || 1.0;

        window.speechSynthesis.speak(utterance);
        return utterance;
    }

    // 停止语音播报
    stopSpeaking() {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
    }

    // 成功提示
    success(message, duration = 3000) {
        this.showToast(message, 'success', duration);
    }

    // 错误提示
    error(message, duration = 5000) {
        this.showToast(message, 'error', duration);
    }

    // 警告提示
    warn(message, duration = 4000) {
        this.showToast(message, 'warning', duration);
    }

    // 信息提示
    info(message, duration = 3000) {
        this.showToast(message, 'info', duration);
    }
}

// 注入 CSS 动画
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
