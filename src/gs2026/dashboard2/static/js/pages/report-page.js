/**
 * Report Center Page - Local File System Support
 */
if (typeof GS2026 === 'undefined') {
    window.GS2026 = { modules: {}, components: {}, pages: {} };
}
if (!GS2026.pages) {
    GS2026.pages = {};
}

GS2026.pages.ReportPage = class ReportPage {
    constructor() {
        this.currentType = null;
        this.currentPage = 1;
        this.pageSize = 20;
        this.reports = [];
        this.init();
    }

    init() {
        this.render();
        this.bindEvents();
        this.loadTypes();
    }

    render() {
        const container = document.getElementById('main-content');
        if (!container) return;

        container.innerHTML = `
            <div class="report-page">
                <div class="report-header">
                    <h1>Report Center</h1>
                    <button class="btn btn-refresh" id="btn-refresh">Refresh</button>
                </div>
                <div class="report-container">
                    <div class="report-sidebar">
                        <div class="type-list" id="type-list"><div class="loading">Loading...</div></div>
                    </div>
                    <div class="report-content">
                        <div class="filter-bar">
                            <div class="filter-left"><h2 id="current-type-name">Select Report Type</h2></div>
                            <div class="filter-right">
                                <input type="text" id="search-input" placeholder="Search..." class="search-input">
                            </div>
                        </div>
                        <div class="report-list" id="report-list">
                            <div class="empty-state"><div class="empty-icon">Folder</div><div class="empty-text">Select a report type</div></div>
                        </div>
                        <div class="pagination" id="pagination" style="display: none;">
                            <button class="btn btn-prev" id="btn-prev">Prev</button>
                            <span class="page-info">Page <span id="current-page">1</span></span>
                            <button class="btn btn-next" id="btn-next">Next</button>
                        </div>
                    </div>
                </div>
                <div class="modal" id="pdf-modal" style="display: none;">
                    <div class="modal-content pdf-modal-content">
                        <div class="modal-header">
                            <h3 id="pdf-title">PDF Preview</h3>
                            <button class="btn-close" id="btn-close-modal">&times;</button>
                        </div>
                        <div class="modal-body"><iframe id="pdf-viewer" class="pdf-iframe"></iframe></div>
                    </div>
                </div>
                <div class="modal" id="reader-modal" style="display: none;">
                    <div class="modal-content reader-modal-content">
                        <div class="modal-header">
                            <h3 id="reader-title">PDF Reader</h3>
                            <button class="btn-close" id="btn-close-reader">&times;</button>
                        </div>
                        <div class="modal-body reader-body">
                            <div class="reader-sidebar">
                                <div class="reader-info">
                                    <div class="info-item"><span class="info-label">Pages:</span><span class="info-value" id="reader-pages">-</span></div>
                                    <div class="info-item"><span class="info-label">Chars:</span><span class="info-value" id="reader-chars">-</span></div>
                                    <div class="info-item"><span class="info-label">Time:</span><span class="info-value" id="reader-time">-</span></div>
                                </div>
                                <div class="tts-section">
                                    <h4>Voice</h4>
                                    <div class="voice-select"><label>Voice:</label><select id="voice-select">
                                        <option value="xiaoxiao">Xiaoxiao</option>
                                        <option value="xiaoyi">Xiaoyi</option>
                                        <option value="yunjian">Yunjian</option>
                                    </select></div>
                                    <div class="speed-select"><label>Speed:</label><input type="range" id="speed-slider" min="0.5" max="2.0" step="0.1" value="1.0"><span id="speed-value">1.0x</span></div>
                                    <div class="tts-actions">
                                        <button class="btn btn-generate-tts" id="btn-generate-tts">Generate</button>
                                        <button class="btn btn-play-tts" id="btn-play-tts" disabled>Play</button>
                                    </div>
                                    <div class="tts-status" id="tts-status"></div>
                                </div>
                            </div>
                            <div class="reader-content"><div class="text-preview" id="text-preview"><div class="loading">Loading...</div></div></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    bindEvents() {
        document.getElementById('btn-refresh')?.addEventListener('click', () => this.loadTypes());
        document.getElementById('search-input')?.addEventListener('input', this.debounce(() => {
            this.currentPage = 1;
            this.loadReports();
        }, 300));
        document.getElementById('btn-prev')?.addEventListener('click', () => {
            if (this.currentPage > 1) { this.currentPage--; this.loadReports(); }
        });
        document.getElementById('btn-next')?.addEventListener('click', () => {
            this.currentPage++; this.loadReports();
        });
        document.getElementById('btn-close-modal')?.addEventListener('click', () => this.closePDFModal());
        document.getElementById('pdf-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'pdf-modal') this.closePDFModal();
        });
        document.getElementById('btn-close-reader')?.addEventListener('click', () => this.closeReaderModal());
        document.getElementById('reader-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'reader-modal') this.closeReaderModal();
        });
        document.getElementById('speed-slider')?.addEventListener('input', (e) => {
            document.getElementById('speed-value').textContent = e.target.value + 'x';
        });
        document.getElementById('btn-generate-tts')?.addEventListener('click', () => this.generateTTS());
        document.getElementById('btn-play-tts')?.addEventListener('click', () => this.playTTS());
    }

    async loadTypes() {
        const container = document.getElementById('type-list');
        container.innerHTML = '<div class="loading">Loading...</div>';
        try {
            const response = await fetch('/api/reports/types');
            const result = await response.json();
            if (result.success) this.renderTypes(result.data);
            else container.innerHTML = '<div class="error">Failed: ' + result.error + '</div>';
        } catch (e) {
            container.innerHTML = '<div class="error">Failed</div>';
        }
    }

    renderTypes(types) {
        const container = document.getElementById('type-list');
        if (types.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-text">No report directories found</div></div>';
            return;
        }
        container.innerHTML = types.map(type => `
            <div class="type-item ${type.report_type_code === this.currentType ? 'active' : ''}" data-type="${type.report_type_code}">
                <span class="type-icon">${type.report_type_icon}</span>
                <span class="type-name">${type.report_type_name}</span>
                <span class="type-count">${type.file_count}</span>
            </div>
        `).join('');
        container.querySelectorAll('.type-item').forEach(item => {
            item.addEventListener('click', () => this.selectType(item.dataset.type));
        });
    }

    selectType(typeCode) {
        this.currentType = typeCode;
        this.currentPage = 1;
        document.querySelectorAll('.type-item').forEach(item => {
            item.classList.toggle('active', item.dataset.type === typeCode);
        });
        const typeName = document.querySelector(`.type-item[data-type="${typeCode}"] .type-name`)?.textContent || typeCode;
        document.getElementById('current-type-name').textContent = typeName;
        this.loadReports();
    }

    async loadReports() {
        if (!this.currentType) return;
        const listContainer = document.getElementById('report-list');
        listContainer.innerHTML = '<div class="loading">Loading...</div>';
        try {
            const params = new URLSearchParams({ type: this.currentType, page: this.currentPage, pageSize: this.pageSize });
            const keyword = document.getElementById('search-input')?.value;
            if (keyword) params.append('keyword', keyword);
            const response = await fetch('/api/reports/list?' + params);
            const result = await response.json();
            if (result.success) {
                this.reports = result.data.report_list;
                this.renderReports(result.data);
            } else listContainer.innerHTML = '<div class="error">Failed: ' + result.error + '</div>';
        } catch (e) {
            listContainer.innerHTML = '<div class="error">Failed</div>';
        }
    }

    renderReports(data) {
        const container = document.getElementById('report-list');
        const pagination = document.getElementById('pagination');
        if (!data.report_list || data.report_list.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-text">No reports</div></div>';
            pagination.style.display = 'none';
            return;
        }
        container.innerHTML = data.report_list.map(report => {
            const size = this.formatFileSize(report.report_file_size);
            const date = report.report_date || 'Unknown';
            return `
                <div class="report-item" data-id="${report.report_id}">
                    <div class="report-icon">PDF</div>
                    <div class="report-info">
                        <div class="report-name">${report.report_name}</div>
                        <div class="report-meta"><span>${date}</span><span>${size}</span></div>
                    </div>
                    <div class="report-actions">
                        <button class="btn btn-view" data-path="${report.report_id}">View</button>
                        <button class="btn btn-read" data-path="${report.report_id}">Read</button>
                        <button class="btn btn-download" data-path="${report.report_id}">Download</button>
                    </div>
                </div>
            `;
        }).join('');
        container.querySelectorAll('.btn-view').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); this.viewPDF(btn.dataset.path); });
        });
        container.querySelectorAll('.btn-download').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); this.downloadReport(btn.dataset.path); });
        });
        container.querySelectorAll('.btn-read').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); this.openReader(btn.dataset.path); });
        });
        document.getElementById('current-page').textContent = data.report_page;
        pagination.style.display = 'flex';
    }

    viewPDF(filePath) {
        const modal = document.getElementById('pdf-modal');
        const viewer = document.getElementById('pdf-viewer');
        const title = document.getElementById('pdf-title');
        const pathParts = filePath.split(/[\\/]/);
        const fileName = pathParts.pop();
        const dirPath = pathParts.join('/');
        title.textContent = fileName;
        viewer.src = '/api/reports/file/' + encodeURIComponent(fileName) + '/view?path=' + encodeURIComponent(dirPath);
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }

    closePDFModal() {
        document.getElementById('pdf-modal').style.display = 'none';
        document.getElementById('pdf-viewer').src = '';
        document.body.style.overflow = '';
    }

    downloadReport(filePath) {
        const pathParts = filePath.split(/[\\/]/);
        const fileName = pathParts.pop();
        const dirPath = pathParts.join('/');
        const url = '/api/reports/file/' + encodeURIComponent(fileName) + '/download?path=' + encodeURIComponent(dirPath);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    async openReader(filePath) {
        this.currentReaderFile = filePath;
        document.getElementById('reader-modal').style.display = 'block';
        document.body.style.overflow = 'hidden';
        const pathParts = filePath.split(/[\\/]/);
        const name = pathParts.pop();
        const dirPath = pathParts.join('/');
        document.getElementById('reader-title').textContent = 'Read: ' + name;
        try {
            const summaryRes = await fetch('/api/reports/file/' + encodeURIComponent(name) + '/summary?path=' + encodeURIComponent(dirPath));
            const summary = await summaryRes.json();
            if (summary.success) {
                document.getElementById('reader-pages').textContent = summary.data.total_pages;
                document.getElementById('reader-chars').textContent = summary.data.total_chars.toLocaleString();
                document.getElementById('reader-time').textContent = summary.data.estimated_reading_time + ' min';
            }
            const textRes = await fetch('/api/reports/file/' + encodeURIComponent(name) + '/text?path=' + encodeURIComponent(dirPath) + '&max_pages=2');
            const textData = await textRes.json();
            if (textData.success) {
                const previewText = textData.data.text.substring(0, 1000);
                document.getElementById('text-preview').innerHTML = '<pre>' + this.escapeHtml(previewText) + (textData.data.text.length > 1000 ? '\n\n...' : '') + '</pre>';
            }
            const ttsRes = await fetch('/api/reports/file/' + encodeURIComponent(name) + '/tts/status?path=' + encodeURIComponent(dirPath));
            const ttsData = await ttsRes.json();
            if (ttsData.success && ttsData.data.exists) {
                this.currentTTSUrl = ttsData.data.audio_url;
                document.getElementById('btn-play-tts').disabled = false;
                document.getElementById('tts-status').textContent = 'Voice ready';
            } else {
                document.getElementById('tts-status').textContent = 'No voice';
            }
        } catch (e) {
            document.getElementById('text-preview').innerHTML = '<div class="error">Failed</div>';
        }
    }

    closeReaderModal() {
        if (this.audioPlayer) { this.audioPlayer.pause(); this.audioPlayer = null; }
        document.getElementById('reader-modal').style.display = 'none';
        document.body.style.overflow = '';
        this.currentReaderFile = null;
        this.currentTTSUrl = null;
    }

    async generateTTS() {
        if (!this.currentReaderFile) return;
        document.getElementById('btn-generate-tts').disabled = true;
        document.getElementById('tts-status').textContent = 'Generating...';
        const pathParts = this.currentReaderFile.split(/[\\/]/);
        const fileName = pathParts.pop();
        const dirPath = pathParts.join('/');
        const voice = document.getElementById('voice-select').value;
        const speed = document.getElementById('speed-slider').value;
        try {
            const response = await fetch('/api/reports/file/' + encodeURIComponent(fileName) + '/tts/generate?path=' + encodeURIComponent(dirPath), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice, speed: parseFloat(speed) })
            });
            const result = await response.json();
            if (result.success) {
                this.currentTTSUrl = result.data.audio_url;
                document.getElementById('btn-play-tts').disabled = false;
                document.getElementById('tts-status').textContent = 'Done (' + result.data.duration + 's)';
            } else {
                document.getElementById('tts-status').textContent = 'Failed: ' + result.error;
            }
        } catch (e) {
            document.getElementById('tts-status').textContent = 'Failed';
        } finally {
            document.getElementById('btn-generate-tts').disabled = false;
        }
    }

    playTTS() {
        if (!this.currentTTSUrl) return;
        if (!this.audioPlayer) this.audioPlayer = new Audio(this.currentTTSUrl);
        const btn = document.getElementById('btn-play-tts');
        if (this.audioPlayer.paused) {
            this.audioPlayer.play();
            btn.textContent = 'Pause';
        } else {
            this.audioPlayer.pause();
            btn.textContent = 'Play';
        }
        this.audioPlayer.onended = () => { btn.textContent = 'Play'; };
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    debounce(fn, delay) {
        let timer = null;
        return function(...args) {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }
};

GS2026.registerPage('report', GS2026.pages.ReportPage);
