/**
 * 报告管理器
 */
GS2026.modules.ReportManager = class ReportManager extends GS2026.modules.BaseManager {
    constructor() {
        super();
        this.baseUrl = '/api/reports';
    }
    
    /**
     * 获取报告类型列表
     */
    async getReportTypes() {
        return this.request('GET', `${this.baseUrl}/types`);
    }
    
    /**
     * 获取报告列表
     * @param {Object} filters - 筛选条件
     * @param {string} filters.type - 报告类型
     * @param {string} filters.format - 文件格式
     * @param {number} filters.page - 页码
     * @param {number} filters.pageSize - 每页数量
     * @param {string} filters.startDate - 开始日期
     * @param {string} filters.endDate - 结束日期
     * @param {string} filters.keyword - 搜索关键词
     */
    async listReports(filters = {}) {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.append(key, value);
            }
        });
        
        const query = params.toString();
        const url = query ? `${this.baseUrl}/list?${query}` : `${this.baseUrl}/list`;
        
        return this.request('GET', url);
    }
    
    /**
     * 获取报告详情
     * @param {number} reportId - 报告ID
     */
    async getReport(reportId) {
        return this.request('GET', `${this.baseUrl}/${reportId}`);
    }
    
    /**
     * 查看报告文件
     * @param {number} reportId - 报告ID
     */
    async viewReportFile(reportId) {
        return this.request('GET', `${this.baseUrl}/file/${reportId}/view`);
    }
    
    /**
     * 生成语音播报
     * @param {number} reportId - 报告ID
     * @param {Object} options - 选项
     * @param {string} options.voice - 音色
     * @param {number} options.speed - 语速
     */
    async generateTTS(reportId, options = {}) {
        return this.request('POST', `${this.baseUrl}/${reportId}/tts/generate`, options);
    }
    
    /**
     * 获取语音生成状态
     * @param {number} reportId - 报告ID
     */
    async getTTSStatus(reportId) {
        return this.request('GET', `${this.baseUrl}/${reportId}/tts/status`);
    }
    
    /**
     * 获取语音文件URL
     * @param {number} reportId - 报告ID
     */
    getTTSAudioUrl(reportId) {
        return `${this.baseUrl}/${reportId}/tts/audio`;
    }
    
    /**
     * 生成报告
     * @param {Object} params - 生成参数
     * @param {string} params.type - 报告类型
     * @param {string} params.date - 报告日期
     * @param {string} params.format - 文件格式（可选）
     * @param {Object} params.params - 其他参数
     */
    async generateReport(params) {
        return this.request('POST', `${this.baseUrl}/generate`, params);
    }
    
    /**
     * 获取任务状态
     * @param {string} taskId - 任务ID
     */
    async getTaskStatus(taskId) {
        return this.request('GET', `${this.baseUrl}/tasks/${taskId}/status`);
    }
    
    /**
     * 删除报告
     * @param {number} reportId - 报告ID
     */
    async deleteReport(reportId) {
        return this.request('DELETE', `${this.baseUrl}/${reportId}`);
    }
};
