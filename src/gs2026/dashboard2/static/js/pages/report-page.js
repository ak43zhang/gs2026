/**
 * Report Center Page
 * File system based report management
 */

(function() {
    'use strict';

    // Report Reader Manager
    const ReportReader = {
        // State
        currentReport: null,
        segments: [],
        currentSegment: 0,
        isPlaying: false,
        audio: null,
        segmentStrategy: localStorage.getItem('tts_strategy') || 'smart', // 默认智能分段
        
        // DOM Elements
        elements: {},
        
        /**
         * Initialize reader
         */
        init: function() {
            this.cacheElements();
            this.bindEvents();
        },
        
        /**
         * Cache DOM elements
         */
        cacheElements: function() {
            this.elements = {
                reader: document.getElementById('report-reader'),
                readerTitle: document.getElementById('reader-title'),
                readerText: document.getElementById('reader-text'),
                voiceSelect: document.getElementById('voice-select'),
                speedSelect: document.getElementById('speed-select'),
                strategySelect: document.getElementById('strategy-select'),
                currentSpan: document.getElementById('reader-current'),
                totalSpan: document.getElementById('reader-total'),
                playBtn: document.getElementById('reader-play'),
                pauseBtn: document.getElementById('reader-pause'),
                prevBtn: document.getElementById('reader-prev'),
                nextBtn: document.getElementById('reader-next'),
                audio: document.getElementById('reader-audio')
            };
            this.audio = this.elements.audio;
            
            // 设置策略选择器初始值
            if (this.elements.strategySelect) {
                this.elements.strategySelect.value = this.segmentStrategy;
            }
        },
        
        /**
         * Bind event handlers
         */
        bindEvents: function() {
            // Close reader
            const closeBtn = document.getElementById('close-reader');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.close());
            }
            
            // Play/Pause
            if (this.elements.playBtn) {
                this.elements.playBtn.addEventListener('click', () => this.play());
            }
            if (this.elements.pauseBtn) {
                this.elements.pauseBtn.addEventListener('click', () => this.pause());
            }
            
            // Prev/Next
            if (this.elements.prevBtn) {
                this.elements.prevBtn.addEventListener('click', () => this.prev());
            }
            if (this.elements.nextBtn) {
                this.elements.nextBtn.addEventListener('click', () => this.next());
            }
            
            // Audio ended
            if (this.audio) {
                this.audio.addEventListener('ended', () => this.onAudioEnded());
            }
            
            // Strategy change
            if (this.elements.strategySelect) {
                this.elements.strategySelect.addEventListener('change', (e) => {
                    this.changeStrategy(e.target.value);
                });
            }
        },
        
        /**
         * Change segmentation strategy
         */
        changeStrategy: function(strategy) {
            this.segmentStrategy = strategy;
            localStorage.setItem('tts_strategy', strategy);
            
            // Reload content with new strategy
            if (this.currentReport) {
                this.loadContent(this.currentReport.type, this.currentReport.filename);
            }
        },
        
        /**
         * Open reader for a report
         */
        open: function(reportType, filename, reportName) {
            this.currentReport = { type: reportType, filename: filename, name: reportName };
            this.currentSegment = 0;
            this.isPlaying = false;
            
            // Update title
            if (this.elements.readerTitle) {
                this.elements.readerTitle.textContent = '阅读: ' + reportName;
            }
            
            // Show reader
            if (this.elements.reader) {
                this.elements.reader.classList.add('active');
            }
            
            // Load content
            this.loadContent(reportType, filename);
        },
        
        /**
         * Close reader
         */
        close: function() {
            this.pause();
            if (this.elements.reader) {
                this.elements.reader.classList.remove('active');
            }
            this.segments = [];
            this.currentSegment = 0;
        },
        
        /**
         * Load report content
         */
        loadContent: function(reportType, filename) {
            // Show loading
            if (this.elements.readerText) {
                this.elements.readerText.innerHTML = '<div class="loading">加载中...</div>';
            }
            
            // 使用当前策略加载内容
            const strategy = this.segmentStrategy || 'smart';
            const url = '/api/reports/' + encodeURIComponent(reportType) + '/' + encodeURIComponent(filename) + '/content?strategy=' + strategy;
            
            fetch(url)
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        this.segments = result.data.segments;
                        this.renderSegments();
                        this.updateProgress();
                        
                        // 显示当前使用的策略
                        console.log('Loaded with strategy:', result.data.strategy);
                        
                        // Prepare TTS
                        this.prepareTTS();
                    } else {
                        this.showError('加载失败: ' + result.error);
                    }
                })
                .catch(error => {
                    console.error('Error loading content:', error);
                    this.showError('网络错误');
                });
        },
        
        /**
         * Prepare TTS audio
         */
        prepareTTS: function() {
            if (!this.currentReport) return;
            
            const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
            const speed = this.elements.speedSelect ? parseFloat(this.elements.speedSelect.value) : 1.0;
            const strategy = this.segmentStrategy || 'smart';  // 使用当前策略
            
            fetch('/api/reports/' + encodeURIComponent(this.currentReport.type) + '/' + encodeURIComponent(this.currentReport.filename) + '/tts/prepare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voice, speed: speed, strategy: strategy })  // 传递策略参数
            })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        // Update segments with audio URLs
                        result.data.segments.forEach((seg, idx) => {
                            if (this.segments[idx]) {
                                this.segments[idx].audio_url = seg.audio_url;
                                this.segments[idx].duration = seg.duration;
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('Error preparing TTS:', error);
                });
        },
        
        /**
         * Render text segments
         */
        renderSegments: function() {
            if (!this.elements.readerText) return;
            
            if (this.segments.length === 0) {
                this.elements.readerText.innerHTML = '<div class="empty">无文本内容</div>';
                return;
            }
            
            const html = this.segments.map((seg, idx) => `
                <div class="reader-segment ${idx === this.currentSegment ? 'active' : ''}" 
                     data-index="${idx}"
                     onclick="ReportReader.goTo(${idx})">
                    <span class="segment-number">${idx + 1}</span>
                    <span class="segment-text">${this.escapeHtml(seg.text)}</span>
                </div>
            `).join('');
            
            this.elements.readerText.innerHTML = html;
        },
        
        /**
         * Go to specific segment
         */
        goTo: function(index) {
            if (index < 0 || index >= this.segments.length) return;
            
            this.currentSegment = index;
            this.highlightSegment();
            this.updateProgress();
            
            if (this.isPlaying) {
                this.playCurrent();
            }
        },
        
        /**
         * Highlight current segment
         */
        highlightSegment: function() {
            const segments = this.elements.readerText.querySelectorAll('.reader-segment');
            segments.forEach((seg, idx) => {
                seg.classList.remove('active');
                if (idx < this.currentSegment) {
                    seg.classList.add('played');
                } else {
                    seg.classList.remove('played');
                }
            });
            
            const current = segments[this.currentSegment];
            if (current) {
                current.classList.add('active');
                current.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        },
        
        /**
         * Update progress display
         */
        updateProgress: function() {
            if (this.elements.currentSpan) {
                this.elements.currentSpan.textContent = this.currentSegment + 1;
            }
            if (this.elements.totalSpan) {
                this.elements.totalSpan.textContent = this.segments.length;
            }
        },
        
        /**
         * Play audio
         */
        play: function() {
            this.isPlaying = true;
            this.elements.playBtn.style.display = 'none';
            this.elements.pauseBtn.style.display = 'flex';
            this.playCurrent();
        },
        
        /**
         * Pause audio
         */
        pause: function() {
            this.isPlaying = false;
            if (this.audio) {
                this.audio.pause();
            }
            if (this.elements.playBtn) {
                this.elements.playBtn.style.display = 'flex';
            }
            if (this.elements.pauseBtn) {
                this.elements.pauseBtn.style.display = 'none';
            }
        },
        
        /**
         * Play current segment
         */
        playCurrent: function() {
            if (!this.segments[this.currentSegment]) return;
            
            const seg = this.segments[this.currentSegment];
            if (!seg.audio_url || !this.audio) return;
            
            // Show loading
            if (this.elements.playBtn) {
                this.elements.playBtn.innerHTML = '&#9203;';
            }
            
            // First, ensure audio is generated
            const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
            const speed = this.elements.speedSelect ? parseFloat(this.elements.speedSelect.value) : 1.0;
            
            fetch('/api/reports/tts/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: seg.text,
                    voice: voice,
                    speed: speed
                })
            })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        // Audio generated, now play
                        this.audio.src = seg.audio_url;
                        this.audio.play().then(() => {
                            if (this.elements.playBtn) {
                                this.elements.playBtn.innerHTML = '&#9654;';
                            }
                        }).catch(err => {
                            console.error('Play error:', err);
                            if (this.elements.playBtn) {
                                this.elements.playBtn.innerHTML = '&#9654;';
                            }
                        });
                    } else {
                        console.error('TTS generation failed:', result.error);
                        if (this.elements.playBtn) {
                            this.elements.playBtn.innerHTML = '&#9654;';
                        }
                    }
                })
                .catch(error => {
                    console.error('Error generating TTS:', error);
                    if (this.elements.playBtn) {
                        this.elements.playBtn.innerHTML = '&#9654;';
                    }
                });
            
            this.highlightSegment();
        },
        
        /**
         * Audio ended handler
         */
        onAudioEnded: function() {
            if (this.currentSegment < this.segments.length - 1) {
                this.currentSegment++;
                this.playCurrent();
                this.updateProgress();
            } else {
                this.pause();
            }
        },
        
        /**
         * Previous segment
         */
        prev: function() {
            if (this.currentSegment > 0) {
                this.goTo(this.currentSegment - 1);
            }
        },
        
        /**
         * Next segment
         */
        next: function() {
            if (this.currentSegment < this.segments.length - 1) {
                this.goTo(this.currentSegment + 1);
            }
        },
        
        /**
         * Show error message
         */
        showError: function(message) {
            if (this.elements.readerText) {
                this.elements.readerText.innerHTML = '<div class="error">' + message + '</div>';
            }
        },
        
        /**
         * Escape HTML
         */
        escapeHtml: function(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };

    // Report Center Manager
    const ReportCenter = {
        // State
        currentType: null,
        reports: [],
        types: [],
        
        // DOM Elements
        elements: {},
        
        /**
         * Initialize report center
         */
        init: function() {
            this.cacheElements();
            this.bindEvents();
            this.loadReportTypes();
            
            // Initialize reader
            ReportReader.init();
        },
        
        /**
         * Cache DOM elements
         */
        cacheElements: function() {
            this.elements = {
                typeList: document.getElementById('report-type-list'),
                reportList: document.getElementById('report-list'),
                reportViewer: document.getElementById('report-viewer'),
                reportFrame: document.getElementById('report-frame'),
                viewerTitle: document.getElementById('viewer-title'),
                searchInput: document.getElementById('search-input'),
                breadcrumb: document.getElementById('breadcrumb'),
                emptyState: document.getElementById('empty-state'),
                loadingState: document.getElementById('loading-state')
            };
        },
        
        /**
         * Bind event handlers
         */
        bindEvents: function() {
            // Search input
            if (this.elements.searchInput) {
                this.elements.searchInput.addEventListener('input', this.debounce((e) => {
                    this.handleSearch(e.target.value);
                }, 300));
            }
            
            // Close viewer button
            const closeBtn = document.getElementById('close-viewer');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.closeViewer());
            }
        },
        
        /**
         * Load report types from server
         */
        loadReportTypes: function() {
            this.showLoading(true);
            
            fetch('/api/reports/types')
                .then(response => response.json())
                .then(result => {
                    this.showLoading(false);
                    
                    if (result.success) {
                        this.types = result.data;
                        this.renderTypeList();
                        
                        // Auto-select first type if available
                        if (this.types.length > 0) {
                            this.selectType(this.types[0].code);
                        }
                    } else {
                        this.showError('Failed to load report types');
                    }
                })
                .catch(error => {
                    this.showLoading(false);
                    console.error('Error loading report types:', error);
                    this.showError('Network error');
                });
        },
        
        /**
         * Render type list sidebar
         */
        renderTypeList: function() {
            if (!this.elements.typeList) return;
            
            if (this.types.length === 0) {
                this.elements.typeList.innerHTML = '<div class="empty-types">未找到报告目录</div>';
                return;
            }
            
            const html = this.types.map(type => `
                <div class="type-item ${type.code === this.currentType ? 'active' : ''}" 
                     data-code="${type.code}"
                     onclick="ReportCenter.selectType('${type.code}')">
                    <span class="type-icon">&#128196;</span>
                    <span class="type-name">${this.escapeHtml(type.name)}</span>
                    <span class="type-count">${type.count}</span>
                </div>
            `).join('');
            
            this.elements.typeList.innerHTML = html;
        },
        
        /**
         * Select a report type
         */
        selectType: function(typeCode) {
            this.currentType = typeCode;
            this.renderTypeList(); // Re-render to update active state
            this.loadReports(typeCode);
            this.updateBreadcrumb(typeCode);
        },
        
        /**
         * Load reports for selected type
         */
        loadReports: function(typeCode) {
            this.showLoading(true);
            
            fetch(`/api/reports/list?type=${encodeURIComponent(typeCode)}`)
                .then(response => response.json())
                .then(result => {
                    this.showLoading(false);
                    
                    if (result.success) {
                        this.reports = result.data.reports;
                        this.renderReportList();
                    } else {
                        this.showError('Failed to load reports');
                    }
                })
                .catch(error => {
                    this.showLoading(false);
                    console.error('Error loading reports:', error);
                    this.showError('Network error');
                });
        },
        
        /**
         * Render report list
         */
        renderReportList: function() {
            if (!this.elements.reportList) return;
            
            if (this.reports.length === 0) {
                this.elements.reportList.innerHTML = '';
                this.showEmpty(true);
                return;
            }
            
            this.showEmpty(false);
            
            const html = this.reports.map(report => `
                <div class="report-card" onclick="ReportCenter.openReport('${report.type}', '${report.filename}')">
                    <div class="report-icon">&#128196;</div>
                    <div class="report-info">
                        <div class="report-name">${this.escapeHtml(report.name)}</div>
                        <div class="report-meta">
                            <span class="report-size">${report.size_formatted}</span>
                            <span class="report-date">${report.modified_time_formatted}</span>
                        </div>
                    </div>
                    <div class="report-actions">
                        <button class="btn-icon" onclick="event.stopPropagation(); ReportCenter.downloadReport('${report.type}', '${report.filename}')" title="Download">
                            &#11015;
                        </button>
                    </div>
                </div>
            `).join('');
            
            this.elements.reportList.innerHTML = html;
        },
        
        /**
         * Open report in viewer
         */
        openReport: function(type, filename) {
            if (!this.elements.reportViewer || !this.elements.reportFrame) return;
            
            const report = this.reports.find(r => r.type === type && r.filename === filename);
            if (!report) return;
            
            // Store current report for reader
            this.currentReport = report;
            
            // Update viewer title
            if (this.elements.viewerTitle) {
                this.elements.viewerTitle.textContent = report.name;
            }
            
            // Set iframe source to PDF file
            const pdfUrl = `/api/reports/file?type=${encodeURIComponent(type)}&filename=${encodeURIComponent(filename)}`;
            this.elements.reportFrame.src = pdfUrl;
            
            // Bind read button
            const readBtn = document.getElementById('read-report-btn');
            if (readBtn) {
                readBtn.onclick = () => {
                    ReportReader.open(type, filename, report.name);
                };
            }
            
            // Show viewer
            this.elements.reportViewer.classList.add('active');
        },
        
        /**
         * Close report viewer
         */
        closeViewer: function() {
            if (!this.elements.reportViewer || !this.elements.reportFrame) return;
            
            this.elements.reportViewer.classList.remove('active');
            this.elements.reportFrame.src = '';
        },
        
        /**
         * Download report
         */
        downloadReport: function(type, filename) {
            const url = `/api/reports/download?type=${encodeURIComponent(type)}&filename=${encodeURIComponent(filename)}`;
            window.open(url, '_blank');
        },
        
        /**
         * Handle search
         */
        handleSearch: function(keyword) {
            if (!keyword.trim()) {
                // Reset to current type view
                if (this.currentType) {
                    this.loadReports(this.currentType);
                }
                return;
            }
            
            this.showLoading(true);
            
            fetch(`/api/reports/search?keyword=${encodeURIComponent(keyword)}`)
                .then(response => response.json())
                .then(result => {
                    this.showLoading(false);
                    
                    if (result.success) {
                        this.reports = result.data.reports;
                        this.renderReportList();
                        this.updateBreadcrumb('搜索: ' + keyword);
                    }
                })
                .catch(error => {
                    this.showLoading(false);
                    console.error('Error searching:', error);
                });
        },
        
        /**
         * Update breadcrumb
         */
        updateBreadcrumb: function(text) {
            if (this.elements.breadcrumb) {
                this.elements.breadcrumb.textContent = text;
            }
        },
        
        /**
         * Show/hide loading state
         */
        showLoading: function(show) {
            if (this.elements.loadingState) {
                this.elements.loadingState.style.display = show ? 'flex' : 'none';
            }
        },
        
        /**
         * Show/hide empty state
         */
        showEmpty: function(show) {
            if (this.elements.emptyState) {
                this.elements.emptyState.style.display = show ? 'flex' : 'none';
            }
        },
        
        /**
         * Show error message
         */
        showError: function(message) {
            if (this.elements.reportList) {
                this.elements.reportList.innerHTML = `<div class="error-message">${this.escapeHtml(message)}</div>`;
            }
        },
        
        /**
         * Escape HTML special characters
         */
        escapeHtml: function(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },
        
        /**
         * Debounce function
         */
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    };

    // Expose to global scope
    window.ReportCenter = ReportCenter;

    // Auto-initialize if GS2026 framework exists
    if (window.GS2026 && window.GS2026.registerPage) {
        window.GS2026.registerPage('report', {
            init: function() {
                ReportCenter.init();
            }
        });
    } else {
        // Fallback: auto-init on DOM ready
        document.addEventListener('DOMContentLoaded', function() {
            ReportCenter.init();
        });
    }

})();
