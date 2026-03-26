/**
 * Logger - 日志系统
 * 统一的日志管理，支持多级别和多输出目标
 */

class Logger {
    constructor(config = {}) {
        this.level = config.level || 'info';
        this.enableConsole = config.enableConsole !== false;
        this.levels = {
            debug: 0,
            info: 1,
            warn: 2,
            error: 3
        };
    }

    // 检查日志级别
    shouldLog(level) {
        return this.levels[level] >= this.levels[this.level];
    }

    // 格式化日志
    format(level, message, meta = {}) {
        const timestamp = new Date().toISOString();
        const metaStr = Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : '';
        return `[${timestamp}] [${level.toUpperCase()}] ${message}${metaStr}`;
    }

    // 输出日志
    output(level, message, meta) {
        if (!this.shouldLog(level)) return;

        const formatted = this.format(level, message, meta);

        if (this.enableConsole) {
            const consoleMethod = level === 'debug' ? 'log' : level;
            console[consoleMethod](formatted);
        }

        // 触发全局日志事件
        if (GS2026 && GS2026.eventBus) {
            GS2026.emit('log', { level, message, meta, timestamp: new Date() });
        }
    }

    debug(message, meta) {
        this.output('debug', message, meta);
    }

    info(message, meta) {
        this.output('info', message, meta);
    }

    warn(message, meta) {
        this.output('warn', message, meta);
    }

    error(message, meta) {
        this.output('error', message, meta);
    }
}
