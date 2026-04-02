/**
 * Report Center Page
 * File system based report management
 */

(function() {
    'use strict';

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
            
            // Update viewer title
            if (this.elements.viewerTitle) {
                this.elements.viewerTitle.textContent = report.name;
            }
            
            // Set iframe source to PDF file
            const pdfUrl = `/api/reports/file?type=${encodeURIComponent(type)}&filename=${encodeURIComponent(filename)}`;
            this.elements.reportFrame.src = pdfUrl;
            
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
