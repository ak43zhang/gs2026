/**
 * ApiClient - API 封装
 * 统一的 HTTP 请求管理，支持拦截器和错误处理
 */

class ApiClient {
    constructor(config = {}) {
        this.baseUrl = config.baseUrl || '/api';
        this.timeout = config.timeout || 30000;
        this.retryCount = config.retryCount || 3;
        this.interceptors = {
            request: [],
            response: []
        };
    }

    // 添加请求拦截器
    addRequestInterceptor(interceptor) {
        this.interceptors.request.push(interceptor);
    }

    // 添加响应拦截器
    addResponseInterceptor(interceptor) {
        this.interceptors.response.push(interceptor);
    }

    // 构建完整URL
    buildUrl(path) {
        if (path.startsWith('http')) return path;
        return `${this.baseUrl}${path.startsWith('/') ? path : '/' + path}`;
    }

    // 执行请求拦截器
    async applyRequestInterceptors(config) {
        for (const interceptor of this.interceptors.request) {
            config = await interceptor(config);
        }
        return config;
    }

    // 执行响应拦截器
    async applyResponseInterceptors(response) {
        for (const interceptor of this.interceptors.response) {
            response = await interceptor(response);
        }
        return response;
    }

    // 基础请求
    async request(method, path, data = null, options = {}) {
        const url = this.buildUrl(path);
        
        let config = {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        if (data && method !== 'GET') {
            config.body = JSON.stringify(data);
        }

        // 应用请求拦截器
        config = await this.applyRequestInterceptors(config);

        // 重试逻辑
        let lastError;
        for (let i = 0; i < this.retryCount; i++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), this.timeout);
                
                const response = await fetch(url, {
                    ...config,
                    signal: controller.signal
                });
                
                clearTimeout(timeoutId);

                // 应用响应拦截器
                const processedResponse = await this.applyResponseInterceptors(response);

                if (!processedResponse.ok) {
                    throw new Error(`HTTP ${processedResponse.status}: ${processedResponse.statusText}`);
                }

                return await processedResponse.json();
            } catch (e) {
                lastError = e;
                if (i < this.retryCount - 1) {
                    await this.sleep(1000 * (i + 1)); // 指数退避
                }
            }
        }

        throw lastError;
    }

    // HTTP 方法
    get(path, options = {}) {
        return this.request('GET', path, null, options);
    }

    post(path, data, options = {}) {
        return this.request('POST', path, data, options);
    }

    put(path, data, options = {}) {
        return this.request('PUT', path, data, options);
    }

    delete(path, options = {}) {
        return this.request('DELETE', path, null, options);
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}
