/**
 * Report Center Page
 * File system based report management
 * Version: 20250407-2 (force cache refresh)
 */

(function() {
    'use strict';
    
    // Force clear cache on version change
    const CURRENT_VERSION = '20250409-1';  // Updated for extract_text fix
    const storedVersion = localStorage.getItem('report_page_version');
    if (storedVersion !== CURRENT_VERSION) {
        console.log('Version changed, clearing caches...');
        localStorage.removeItem('tts_strategy');
        localStorage.setItem('report_page_version', CURRENT_VERSION);
    }

    // Report Reader Manager
    const ReportReader = {
        // State
        currentReport: null,
        segments: [],
        currentSegment: 0,
        isPlaying: false,
        audio: null,
        segmentStrategy: localStorage.getItem('tts_strategy') || 'original', // 默认按句分割
        

        
        /**
         * Force reset strategy to ensure consistency
         */
        resetStrategy: function() {
            // Clear localStorage to force default strategy
            localStorage.removeItem('tts_strategy');
            this.segmentStrategy = 'original';
            if (this.elements.strategySelect) {
                this.elements.strategySelect.value = 'original';
            }
            console.log('Strategy reset to original');
        },
        
        // DOM Elements
        elements: {},
        _initialized: false,
        
        /**
         * Initialize reader
         */
        init: function() {
            if (this._initialized) {
                console.log('ReportReader already initialized, skipping');
                return;
            }
            this._initialized = true;
            console.log('ReportReader initializing...');
            this.cacheElements();
            this.bindEvents();
            console.log('ReportReader initialized');
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
                audio: document.getElementById('reader-audio'),
                // 新增元素
                loadingBar: document.getElementById('tts-loading-bar'),
                progressFill: document.getElementById('tts-progress-fill'),
                loadingText: document.getElementById('tts-loading-text'),
                jumpInput: document.getElementById('jump-input'),
                jumpBtn: document.getElementById('reader-jump'),
                jumpAutoPlay: document.getElementById('jump-auto-play')
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
            
            // Play/Pause - with duplicate binding protection
            if (this.elements.playBtn && !this.elements.playBtn._hasClickHandler) {
                this.elements.playBtn._hasClickHandler = true;
                this.elements.playBtn.addEventListener('click', () => this.play());
            }
            if (this.elements.pauseBtn && !this.elements.pauseBtn._hasClickHandler) {
                this.elements.pauseBtn._hasClickHandler = true;
                this.elements.pauseBtn.addEventListener('click', () => this.pause());
            }
            
            // Prev/Next - with duplicate binding protection
            if (this.elements.prevBtn && !this.elements.prevBtn._hasClickHandler) {
                this.elements.prevBtn._hasClickHandler = true;
                this.elements.prevBtn.addEventListener('click', () => this.prev());
            }
            if (this.elements.nextBtn && !this.elements.nextBtn._hasClickHandler) {
                this.elements.nextBtn._hasClickHandler = true;
                this.elements.nextBtn.addEventListener('click', () => this.next());
            }
            
            // Audio ended - handled in _playAudioWithRetry with onended callback
            // Note: The ended event is now managed per-playback in _playAudioWithRetry
            
            // Strategy change
            if (this.elements.strategySelect) {
                this.elements.strategySelect.addEventListener('change', (e) => {
                    this.changeStrategy(e.target.value);
                });
            }
            
            // Jump to segment - use event delegation to avoid duplicate bindings
            const jumpBtn = document.getElementById('reader-jump');
            const jumpInput = document.getElementById('jump-input');
            
            if (jumpBtn && !jumpBtn._hasJumpHandler) {
                jumpBtn._hasJumpHandler = true;
                jumpBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.handleJump();
                });
            }
            
            if (jumpInput && !jumpInput._hasEnterHandler) {
                jumpInput._hasEnterHandler = true;
                jumpInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        e.stopPropagation();
                        this.handleJump();
                    }
                });
            }
            
            // Keyboard shortcuts
            this.bindKeyboardShortcuts();
        },
        
        /**
         * Bind keyboard shortcuts
         */
        bindKeyboardShortcuts: function() {
            document.addEventListener('keydown', (e) => {
                // Only when reader is open
                if (!this.elements.reader || !this.elements.reader.classList.contains('active')) {
                    return;
                }
                
                // Ctrl+G: Jump to segment
                if (e.ctrlKey && e.key === 'g') {
                    e.preventDefault();
                    if (this.elements.jumpInput) {
                        this.elements.jumpInput.focus();
                        this.elements.jumpInput.select();
                    }
                }
                
                // Space: Play/Pause
                if (e.key === ' ' && e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    if (this.isPlaying) {
                        this.pause();
                    } else {
                        this.play();
                    }
                }
                
                // Arrow Left: Previous
                if (e.key === 'ArrowLeft' && e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    this.prev();
                }
                
                // Arrow Right: Next
                if (e.key === 'ArrowRight' && e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    this.next();
                }
            });
        },
        
        // Flag to prevent duplicate jump processing
        _isProcessingJump: false,
        
        /**
         * Handle jump to segment
         */
        handleJump: function() {
            // Prevent duplicate processing
            if (this._isProcessingJump) {
                console.log('Jump already processing, ignoring duplicate');
                return;
            }
            
            // 实时获取输入框元素（避免缓存问题）
            const jumpInput = document.getElementById('jump-input');
            const jumpAutoPlay = document.getElementById('jump-auto-play');
            
            if (!jumpInput) {
                console.error('Jump input not found');
                alert('跳转功能初始化失败，请刷新页面重试');
                return;
            }
            
            // Check if segments are loaded
            if (!this.segments || this.segments.length === 0) {
                alert('报告内容尚未加载完成，请稍后再试');
                return;
            }
            
            const inputValue = jumpInput.value.trim();
            console.log('Jump input value:', inputValue, 'length:', inputValue.length);
            
            // Check if input is empty
            if (!inputValue || inputValue === '') {
                alert('请输入句号');
                jumpInput.focus();
                return;
            }
            
            const targetNum = parseInt(inputValue, 10);
            console.log('Parsed number:', targetNum);
            
            // Check if valid number
            if (isNaN(targetNum) || targetNum < 1) {
                alert('请输入有效的数字（大于0）');
                jumpInput.focus();
                return;
            }
            
            const targetIndex = targetNum - 1; // Convert to 0-based
            console.log('Target index:', targetIndex, 'Total segments:', this.segments.length);
            
            // Check range
            if (targetIndex < 0 || targetIndex >= this.segments.length) {
                alert('请输入有效的句号 (1-' + this.segments.length + ')');
                jumpInput.focus();
                return;
            }
            
            // Set processing flag
            this._isProcessingJump = true;
            
            const autoPlay = jumpAutoPlay ? jumpAutoPlay.checked : true;
            
            // Jump to target segment
            this.goTo(targetIndex);
            
            // Auto play if checked
            if (autoPlay && !this.isPlaying) {
                this.play();
            }
            
            // Clear input
            jumpInput.value = '';
            
            console.log('Jumped to segment ' + (targetIndex + 1));
            
            // Clear flag after a short delay
            setTimeout(() => {
                this._isProcessingJump = false;
            }, 500);
        },
        
        /**
         * Show loading progress
         */
        showLoadingProgress: function(current, total) {
            if (!this.elements.loadingBar || !this.elements.progressFill || !this.elements.loadingText) {
                return;
            }
            
            const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
            
            this.elements.loadingBar.style.display = 'block';
            this.elements.progressFill.style.width = percentage + '%';
            this.elements.loadingText.textContent = '准备语音中... (' + current + '/' + total + ')';
            
            // Hide when complete
            if (current >= total) {
                setTimeout(() => {
                    this.elements.loadingBar.style.display = 'none';
                }, 500);
            }
        },
        
        /**
         * Hide loading progress
         */
        hideLoadingProgress: function() {
            if (this.elements.loadingBar) {
                this.elements.loadingBar.style.display = 'none';
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
            const strategy = this.segmentStrategy || 'original';
            console.log('Loading content with strategy:', strategy);
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
            const strategy = this.segmentStrategy || 'original';  // 使用当前策略
            console.log('Preparing TTS with strategy:', strategy);
            const self = this;
            
            // Show loading progress
            this.showLoadingProgress(0, this.segments.length);
            
            fetch('/api/reports/' + encodeURIComponent(this.currentReport.type) + '/' + encodeURIComponent(this.currentReport.filename) + '/tts/prepare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voice, speed: speed, strategy: strategy })  // 传递策略参数
            })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        const hashMap = result.data.segments;  // {text_hash: audio_info}
                        const indexMap = result.data.index_map;  // {index: audio_info} - reliable matching
                        let matchCount = 0;
                        const total = self.segments.length;
                        
                        // First try index-based matching (most reliable)
                        if (indexMap && Object.keys(indexMap).length > 0) {
                            console.log('Using index-based matching');
                            self.segments.forEach((seg, idx) => {
                                const audioInfo = indexMap[String(idx)];
                                if (audioInfo) {
                                    seg.audio_url = audioInfo.audio_url;
                                    seg.duration = audioInfo.duration;
                                    seg.ready = audioInfo.ready;
                                    matchCount++;
                                }
                                
                                // Update progress every 10 segments
                                if (idx % 10 === 0 || idx === total - 1) {
                                    self.showLoadingProgress(idx + 1, total);
                                }
                            });
                        } else {
                            // Fallback to hash matching
                            console.log('Using hash-based matching');
                            self.segments.forEach((seg, idx) => {
                                const textHash = self._getTextHash(seg.text);
                                const audioInfo = hashMap[textHash];
                                
                                if (audioInfo) {
                                    seg.audio_url = audioInfo.audio_url;
                                    seg.duration = audioInfo.duration;
                                    seg.ready = audioInfo.ready;
                                    matchCount++;
                                }
                                
                                if (idx % 10 === 0 || idx === total - 1) {
                                    self.showLoadingProgress(idx + 1, total);
                                }
                            });
                        }
                        
                        // Hide loading progress
                        setTimeout(() => {
                            self.hideLoadingProgress();
                        }, 500);
                        
                        console.log('TTS prepared: ' + matchCount + '/' + self.segments.length + ' segments matched');
                        
                        // Re-render to show ready status
                        self.renderSegments();
                    }
                })
                .catch(error => {
                    console.error('Error preparing TTS:', error);
                });
        },
        
        /**
         * Get text hash for matching (MD5 - same as backend)
         */
        _getTextHash: function(text) {
            // Use MD5 algorithm (same as backend Python hashlib.md5)
            return this._md5(text);
        },
        
        /**
         * MD5 hash function using Web Crypto API (more reliable)
         */
        _md5: function(string) {
            // Use a simplified but reliable MD5 implementation
            // Based on Joseph Myers' implementation
            
            var hex_chr = '0123456789abcdef';
            
            function rhex(num) {
                var str = '';
                for (var j = 0; j <= 3; j++) {
                    str += hex_chr.charAt((num >> (j * 8 + 4)) & 0x0F) +
                           hex_chr.charAt((num >> (j * 8)) & 0x0F);
                }
                return str;
            }
            
            function str2blks_MD5(str) {
                var nblk = ((str.length + 8) >> 6) + 1;
                var blks = new Array(nblk * 16);
                for (var i = 0; i < nblk * 16; i++) blks[i] = 0;
                for (i = 0; i < str.length; i++) {
                    blks[i >> 2] |= str.charCodeAt(i) << ((i % 4) * 8);
                }
                blks[i >> 2] |= 0x80 << ((i % 4) * 8);
                blks[nblk * 16 - 2] = str.length * 8;
                return blks;
            }
            
            function add(x, y) {
                var lsw = (x & 0xFFFF) + (y & 0xFFFF);
                var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
                return (msw << 16) | (lsw & 0xFFFF);
            }
            
            function rol(num, cnt) {
                return (num << cnt) | (num >>> (32 - cnt));
            }
            
            function cmn(q, a, b, x, s, t) {
                return add(rol(add(add(a, q), add(x, t)), s), b);
            }
            
            function ff(a, b, c, d, x, s, t) {
                return cmn((b & c) | ((~b) & d), a, b, x, s, t);
            }
            
            function gg(a, b, c, d, x, s, t) {
                return cmn((b & d) | (c & (~d)), a, b, x, s, t);
            }
            
            function hh(a, b, c, d, x, s, t) {
                return cmn(b ^ c ^ d, a, b, x, s, t);
            }
            
            function ii(a, b, c, d, x, s, t) {
                return cmn(c ^ (b | (~d)), a, b, x, s, t);
            }
            
            var x = str2blks_MD5(string);
            var a = 1732584193;
            var b = -271733879;
            var c = -1732584194;
            var d = 271733878;
            
            for (var i = 0; i < x.length; i += 16) {
                var olda = a;
                var oldb = b;
                var oldc = c;
                var oldd = d;
                
                a = ff(a, b, c, d, x[i + 0], 7, -680876936);
                d = ff(d, a, b, c, x[i + 1], 12, -389564586);
                c = ff(c, d, a, b, x[i + 2], 17, 606105819);
                b = ff(b, c, d, a, x[i + 3], 22, -1044525330);
                a = ff(a, b, c, d, x[i + 4], 7, -176418897);
                d = ff(d, a, b, c, x[i + 5], 12, 1200080426);
                c = ff(c, d, a, b, x[i + 6], 17, -1473231341);
                b = ff(b, c, d, a, x[i + 7], 22, -45705983);
                a = ff(a, b, c, d, x[i + 8], 7, 1770035416);
                d = ff(d, a, b, c, x[i + 9], 12, -1958414417);
                c = ff(c, d, a, b, x[i + 10], 17, -42063);
                b = ff(b, c, d, a, x[i + 11], 22, -1990404162);
                a = ff(a, b, c, d, x[i + 12], 7, 1804603682);
                d = ff(d, a, b, c, x[i + 13], 12, -40341101);
                c = ff(c, d, a, b, x[i + 14], 17, -1502002290);
                b = ff(b, c, d, a, x[i + 15], 22, 1236535329);
                
                a = gg(a, b, c, d, x[i + 1], 5, -165796510);
                d = gg(d, a, b, c, x[i + 6], 9, -1069501632);
                c = gg(c, d, a, b, x[i + 11], 14, 643717713);
                b = gg(b, c, d, a, x[i + 0], 20, -373897302);
                a = gg(a, b, c, d, x[i + 5], 5, -701558691);
                d = gg(d, a, b, c, x[i + 10], 9, 38016083);
                c = gg(c, d, a, b, x[i + 15], 14, -660478335);
                b = gg(b, c, d, a, x[i + 4], 20, -405537848);
                a = gg(a, b, c, d, x[i + 9], 5, 568446438);
                d = gg(d, a, b, c, x[i + 14], 9, -1019803690);
                c = gg(c, d, a, b, x[i + 3], 14, -187363961);
                b = gg(b, c, d, a, x[i + 8], 20, 1163531501);
                a = gg(a, b, c, d, x[i + 13], 5, -1444681467);
                d = gg(d, a, b, c, x[i + 2], 9, -51403784);
                c = gg(c, d, a, b, x[i + 7], 14, 1735328473);
                b = gg(b, c, d, a, x[i + 12], 20, -1926607734);
                
                a = hh(a, b, c, d, x[i + 5], 4, -378558);
                d = hh(d, a, b, c, x[i + 8], 11, -2022574463);
                c = hh(c, d, a, b, x[i + 11], 16, 1839030562);
                b = hh(b, c, d, a, x[i + 14], 23, -35309556);
                a = hh(a, b, c, d, x[i + 1], 4, -1530992060);
                d = hh(d, a, b, c, x[i + 4], 11, 1272893353);
                c = hh(c, d, a, b, x[i + 7], 16, -155497632);
                b = hh(b, c, d, a, x[i + 10], 23, -1094730640);
                a = hh(a, b, c, d, x[i + 13], 4, 681279174);
                d = hh(d, a, b, c, x[i + 0], 11, -358537222);
                c = hh(c, d, a, b, x[i + 3], 16, -722521979);
                b = hh(b, c, d, a, x[i + 6], 23, 76029189);
                a = hh(a, b, c, d, x[i + 9], 4, -640364487);
                d = hh(d, a, b, c, x[i + 12], 11, -421815835);
                c = hh(c, d, a, b, x[i + 15], 16, 530742520);
                b = hh(b, c, d, a, x[i + 2], 23, -995338651);
                
                a = ii(a, b, c, d, x[i + 0], 6, -198630844);
                d = ii(d, a, b, c, x[i + 7], 10, 1126891415);
                c = ii(c, d, a, b, x[i + 14], 15, -1416354905);
                b = ii(b, c, d, a, x[i + 5], 21, -57434055);
                a = ii(a, b, c, d, x[i + 12], 6, 1700485571);
                d = ii(d, a, b, c, x[i + 3], 10, -1894986606);
                c = ii(c, d, a, b, x[i + 10], 15, -1051523);
                b = ii(b, c, d, a, x[i + 1], 21, -2054922799);
                a = ii(a, b, c, d, x[i + 8], 6, 1873313359);
                d = ii(d, a, b, c, x[i + 15], 10, -30611744);
                c = ii(c, d, a, b, x[i + 6], 15, -1560198380);
                b = ii(b, c, d, a, x[i + 13], 21, 1309151649);
                a = ii(a, b, c, d, x[i + 4], 6, -145523070);
                d = ii(d, a, b, c, x[i + 11], 10, -1120210379);
                c = ii(c, d, a, b, x[i + 2], 15, 718787259);
                b = ii(b, c, d, a, x[i + 9], 21, -343485551);
                
                a = add(a, olda);
                b = add(b, oldb);
                c = add(c, oldc);
                d = add(d, oldd);
            }
            
            return rhex(a) + rhex(b) + rhex(c) + rhex(d);
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
            
            const html = this.segments.map((seg, idx) => {
                // Determine status icon
                let statusIcon = '○';
                let statusClass = 'status-pending';
                if (seg.generating) {
                    statusIcon = '⏳';
                    statusClass = 'status-generating';
                } else if (seg.ready) {
                    statusIcon = '✓';
                    statusClass = 'status-ready';
                } else if (seg.audio_url) {
                    statusIcon = '○';
                    statusClass = 'status-pending';
                }
                
                return `
                <div class="reader-segment ${idx === this.currentSegment ? 'active' : ''}" 
                     data-index="${idx}"
                     onclick="ReportReader.goTo(${idx})">
                    <span class="segment-status ${statusClass}" data-index="${idx}">${statusIcon}</span>
                    <span class="segment-number">${idx + 1}</span>
                    <span class="segment-text">${this.escapeHtml(seg.text)}</span>
                </div>
            `}).join('');
            
            this.elements.readerText.innerHTML = html;
        },
        
        /**
         * Update segment status icon
         */
        updateSegmentStatus: function(index, status) {
            const segment = this.segments[index];
            if (!segment) return;
            
            if (status === 'generating') {
                segment.generating = true;
                segment.ready = false;
            } else if (status === 'ready') {
                segment.generating = false;
                segment.ready = true;
            } else if (status === 'pending') {
                segment.generating = false;
                segment.ready = false;
            }
            
            // Update DOM
            const statusEl = this.elements.readerText.querySelector(`.segment-status[data-index="${index}"]`);
            if (statusEl) {
                let icon = '○';
                let className = 'status-pending';
                if (status === 'generating') {
                    icon = '⏳';
                    className = 'status-generating';
                } else if (status === 'ready') {
                    icon = '✓';
                    className = 'status-ready';
                }
                statusEl.textContent = icon;
                statusEl.className = 'segment-status ' + className;
            }
        },
        
        /**
         * Go to specific segment
         */
        goTo: function(index) {
            console.log('=== goTo() called ===', 'target:', index, 'current:', this.currentSegment);
            if (index < 0 || index >= this.segments.length) {
                console.log('Invalid index, returning');
                return;
            }
            
            this.currentSegment = index;
            console.log('Set currentSegment to:', this.currentSegment);
            this.highlightSegment();
            this.updateProgress();
            
            // Note: We don't auto-play here anymore
            // Manual navigation should not auto-start playback
            // User needs to explicitly click play
            console.log('=== goTo() complete ===');
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
         * Play current segment - Simplified sequential playback
         */
        playCurrent: function() {
            if (!this.segments[this.currentSegment]) return;
            
            const index = this.currentSegment;
            const seg = this.segments[index];
            const self = this;
            
            console.log('=== PlayCurrent called ===', 'index:', index, 'text:', seg.text.substring(0, 50));
            
            // Always ensure audio URL is set
            const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
            const speed = this.elements.speedSelect ? parseFloat(this.elements.speedSelect.value) : 1.0;
            const textHash = this._getTextHash(seg.text);
            seg.audio_url = '/api/reports/tts/audio?text=' + textHash + '&voice=' + voice + '&speed=' + speed;
            
            console.log('Audio URL:', seg.audio_url);
            
            // Update UI
            this.updateSegmentStatus(index, 'generating');
            if (this.elements.playBtn) {
                this.elements.playBtn.innerHTML = '&#9203;';
                this.elements.playBtn.disabled = true;
            }
            
            // Step 1: Generate audio via API
            console.log('Step 1: Generating audio for segment', index);
            fetch('/api/reports/tts/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: seg.text,
                    voice: voice,
                    speed: speed
                })
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .then(result => {
                    if (!result.success) {
                        throw new Error(result.error || 'Generation failed');
                    }
                    console.log('Step 1 complete: Audio generated', result.data);
                    
                    // Update audio URL from result if available
                    if (result.data && result.data.audio_url) {
                        seg.audio_url = result.data.audio_url;
                    }
                    
                    // Step 2: Wait and play
                    setTimeout(function() {
                        self._playAudio(index, seg);
                    }, 500);
                })
                .catch(error => {
                    console.error('Generation failed:', error);
                    // Try to play anyway (might be cached)
                    console.log('Trying to play from cache...');
                    self._playAudio(index, seg);
                });
            
            this.highlightSegment();
        },
        
        /**
         * Play audio with auto-advance
         */
        _playAudio: function(index, seg) {
            const self = this;
            
            console.log('Step 2: Playing audio for segment', index);
            
            // Ensure audio URL is set correctly
            if (!seg.audio_url) {
                const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
                const textHash = this._getTextHash(seg.text);
                seg.audio_url = '/api/reports/tts/audio?text=' + textHash + '&voice=' + voice;
            }
            
            console.log('Audio URL:', seg.audio_url);
            
            // Setup ended handler BEFORE setting src
            this.audio.onended = function() {
                console.log('=== Audio ended for segment', index, '===');
                self._onSegmentFinished(index);
            };
            
            this.audio.onerror = function(e) {
                console.error('Audio error:', e);
                self.updateSegmentStatus(index, 'error');
                self._resetPlayButton();
            };
            
            // Set source and load
            this.audio.src = seg.audio_url;
            this.audio.load();
            
            // Play with retry
            const tryPlay = () => {
                this.audio.play()
                    .then(() => {
                        console.log('Step 2 complete: Audio playing');
                        this.updateSegmentStatus(index, 'ready');
                        this._resetPlayButton();
                    })
                    .catch(err => {
                        console.error('Play failed:', err);
                        self.updateSegmentStatus(index, 'error');
                        self._resetPlayButton();
                    });
            };
            
            // Small delay to ensure audio is loaded
            setTimeout(tryPlay, 100);
        },
        
        /**
         * Called when a segment finishes playing
         */
        _onSegmentFinished: function(finishedIndex) {
            console.log('_onSegmentFinished:', finishedIndex, 'currentSegment:', this.currentSegment, 'isPlaying:', this.isPlaying);
            
            // Only auto-advance if we're still playing and on the expected segment
            if (!this.isPlaying) {
                console.log('Not playing, stopping');
                return;
            }
            
            // Check if user manually navigated away
            if (this.currentSegment !== finishedIndex) {
                console.log('User navigated to different segment, not auto-advancing');
                return;
            }
            
            // Move to next segment
            if (this.currentSegment < this.segments.length - 1) {
                console.log('Auto-advancing to segment', this.currentSegment + 1);
                this.currentSegment++;
                this.highlightSegment();
                this.updateProgress();
                
                // Play next segment
                this.playCurrent();
            } else {
                // End of report
                console.log('End of report');
                this.isPlaying = false;
                this._resetPlayButton();
            }
        },
        
        /**
         * Reset play button state
         */
        _resetPlayButton: function() {
            if (this.elements.playBtn) {
                this.elements.playBtn.innerHTML = '&#9654;';
                this.elements.playBtn.disabled = false;
            }
        },
        
        /**
         * Previous segment
         */
        prev: function() {
            if (this.currentSegment > 0) {
                // Stop current playback before navigating
                this._stopPlayback();
                this.goTo(this.currentSegment - 1);
            }
        },
        
        /**
         * Next segment
         */
        next: function() {
            console.log('=== next() called ===', 'current:', this.currentSegment, 'total:', this.segments.length);
            if (this.currentSegment < this.segments.length - 1) {
                // Stop current playback before navigating
                this._stopPlayback();
                const targetIndex = this.currentSegment + 1;
                console.log('Navigating to index:', targetIndex);
                this.goTo(targetIndex);
                console.log('After goTo, currentSegment:', this.currentSegment);
            } else {
                console.log('Already at last segment');
            }
        },
        
        /**
         * Stop current playback
         */
        _stopPlayback: function() {
            // Stop audio
            if (this.audio) {
                this.audio.pause();
                this.audio.currentTime = 0;
                this.audio.onended = null; // Remove ended handler
            }
            
            // Reset state
            this.isPlaying = false;
            this._resetPlayButton();
            
            console.log('Playback stopped for manual navigation');
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
        _initialized: false,
        
        // DOM Elements
        elements: {},
        
        /**
         * Initialize report center
         */
        init: function() {
            if (this._initialized) {
                console.log('ReportCenter already initialized, skipping');
                return;
            }
            this._initialized = true;
            console.log('ReportCenter initializing...');
            this.cacheElements();
            this.bindEvents();
            this.loadReportTypes();
            
            // Initialize reader
            ReportReader.init();
            console.log('ReportCenter initialized');
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
            this.currentPath = '';  // 【新增】重置子路径
            this.renderTypeList(); // Re-render to update active state
            this.loadReports(typeCode);
            this.updateBreadcrumb(typeCode);
            this._renderSmartToolbar(typeCode);
        },

        /**
         * 智能报告工具栏（仅在"智能报告"类型下显示）
         */
        _renderSmartToolbar: function(typeCode) {
            // 移除旧的工具栏
            const oldBar = document.getElementById('smart-report-toolbar');
            if (oldBar) oldBar.remove();

            if (typeCode !== '智能报告') return;

            const toolbar = document.createElement('div');
            toolbar.id = 'smart-report-toolbar';
            toolbar.style.cssText = 'padding:12px 16px;background:#f0f2ff;border-radius:8px;margin-bottom:14px;display:flex;align-items:center;gap:12px;';
            toolbar.innerHTML = `
                <input type="date" id="smart-report-date" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:14px;" value="${new Date().toISOString().slice(0,10)}">
                <button id="smart-report-btn" style="padding:8px 18px;background:#667eea;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer;font-weight:600;">🚀 生成智能日报</button>
                <span id="smart-report-status" style="font-size:13px;color:#666;"></span>
            `;

            // 插入到列表容器之前
            const container = document.querySelector('.report-list-container');
            if (container) container.parentNode.insertBefore(toolbar, container);

            // 绑定事件
            document.getElementById('smart-report-btn').addEventListener('click', () => {
                this._generateSmartReport();
            });
        },

        _generateSmartReport: function() {
            const dateInput = document.getElementById('smart-report-date');
            const statusEl = document.getElementById('smart-report-status');
            const btn = document.getElementById('smart-report-btn');
            const date = dateInput ? dateInput.value : '';

            btn.disabled = true;
            btn.textContent = '⏳ 生成中...';
            statusEl.textContent = '正在查询数据并生成报告...';

            fetch('/api/reports/smart/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({date: date || null})
            })
            .then(r => r.json())
            .then(result => {
                btn.disabled = false;
                btn.textContent = '🚀 生成智能日报';
                if (result.success) {
                    const s = result.stats;
                    statusEl.textContent = `✅ 生成成功！领域${s.domain} 新闻${s.news} 公告${s.notice} 涨停${s.ztb}`;
                    statusEl.style.color = '#27ae60';
                    // 刷新列表
                    this.loadReports('智能报告');
                } else {
                    statusEl.textContent = '❌ ' + (result.error || '生成失败');
                    statusEl.style.color = '#e74c3c';
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.textContent = '🚀 生成智能日报';
                statusEl.textContent = '❌ 网络错误: ' + err.message;
                statusEl.style.color = '#e74c3c';
            });
        },
        
        /**
         * Load reports for selected type
         */
        loadReports: function(typeCode, subPath) {
            this.showLoading(true);
            if (subPath !== undefined) this.currentPath = subPath;
            const pathParam = this.currentPath ? `&path=${encodeURIComponent(this.currentPath)}` : '';
            
            fetch(`/api/reports/list?type=${encodeURIComponent(typeCode)}${pathParam}`)
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
            
            const html = this.reports.map(report => {
                // 【新增】子目录渲染
                if (report.is_directory || report.format === 'directory') {
                    return `
                        <div class="report-card report-card-dir" onclick="ReportCenter.openDirectory('${this.escapeHtml(report.relative_path)}')" style="cursor:pointer;border-left:3px solid #667eea;">
                            <div class="report-icon">📁</div>
                            <div class="report-info">
                                <div class="report-name" style="font-weight:600;">${this.escapeHtml(report.name)}</div>
                                <div class="report-meta">
                                    <span class="report-size">${report.size_formatted || ''}</span>
                                    <span class="report-date">${report.modified_time_formatted || ''}</span>
                                </div>
                            </div>
                            <div class="report-actions"><span style="color:#999;font-size:20px;">›</span></div>
                        </div>`;
                }
                
                // 文件图标
                const icon = report.format_icon || '📄';
                
                // 【新增】MD/DOCX用内联查看，其他用原来的方式
                const fmt = (report.format || '').toLowerCase();
                const isInline = ['md', 'docx', 'sql', 'txt'].includes(fmt);
                const clickAction = isInline 
                    ? `ReportCenter.openDocInline('${this.escapeHtml(report.relative_path)}', '${this.escapeHtml(report.name)}')`
                    : `ReportCenter.openReport('${report.type}', '${report.filename}')`;
                
                return `
                    <div class="report-card" onclick="${clickAction}">
                        <div class="report-icon">${icon}</div>
                        <div class="report-info">
                            <div class="report-name">${this.escapeHtml(report.name)}</div>
                            <div class="report-meta">
                                <span class="report-format" style="background:#f0f2ff;padding:1px 6px;border-radius:3px;font-size:11px;">${fmt}</span>
                                <span class="report-size">${report.size_formatted}</span>
                                <span class="report-date">${report.modified_time_formatted}</span>
                            </div>
                        </div>
                        <div class="report-actions">
                            <button class="btn-icon" onclick="event.stopPropagation(); ReportCenter.downloadReport('${report.type}', '${report.filename}')" title="Download">
                                &#11015;
                            </button>
                        </div>
                    </div>`;
            }).join('');
            
            this.elements.reportList.innerHTML = html;
            
            // 【新增】更新面包屑导航
            this._updatePathBreadcrumb();
        },
        
        /**
         * 【新增】打开子目录
         */
        openDirectory: function(relativePath) {
            this.currentPath = relativePath;
            this.loadReports(this.currentType);
        },
        
        /**
         * 【新增】内联查看MD/DOCX/TXT文档
         */
        openDocInline: function(relativePath, title) {
            const fullPath = this.currentType + '/' + relativePath;
            
            // 显示viewer
            if (this.elements.reportViewer) {
                this.elements.reportViewer.classList.add('active');
            }
            if (this.elements.viewerTitle) {
                this.elements.viewerTitle.textContent = title || relativePath;
            }
            
            // 使用iframe加载内容
            if (this.elements.reportFrame) {
                this.elements.reportFrame.src = '';
                this.elements.reportFrame.srcdoc = '<div style="padding:20px;font-family:system-ui;color:#666;">加载中...</div>';
            }
            
            // 请求文档内容
            fetch(`/api/reports/doc-content?path=${encodeURIComponent(fullPath)}`)
                .then(r => r.json())
                .then(result => {
                    if (result.success && this.elements.reportFrame) {
                        let htmlContent = '';
                        if (result.type === 'html') {
                            htmlContent = `<!DOCTYPE html><html><head><meta charset="utf-8">
                                <style>
                                    body { font-family: -apple-system, system-ui, sans-serif; padding: 24px 32px; line-height: 1.8; color: #333; max-width: 900px; margin: 0 auto; }
                                    h1,h2,h3 { color: #1a1a1a; margin-top: 1.5em; }
                                    h1 { border-bottom: 2px solid #667eea; padding-bottom: 8px; }
                                    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
                                    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
                                    th { background: #f5f7ff; }
                                    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
                                    pre { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; overflow-x: auto; }
                                    pre code { background: none; color: inherit; }
                                    blockquote { border-left: 4px solid #667eea; margin: 16px 0; padding: 8px 16px; background: #f8f9ff; }
                                    a { color: #667eea; }
                                    img { max-width: 100%; }
                                </style>
                            </head><body>${result.content}</body></html>`;
                        } else if (result.type === 'code') {
                            htmlContent = `<!DOCTYPE html><html><head><meta charset="utf-8">
                                <style>
                                    body { font-family: 'Consolas', monospace; padding: 16px; margin: 0; }
                                    pre { background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; line-height: 1.6; font-size: 13px; }
                                </style>
                            </head><body><pre>${this.escapeHtml(result.content)}</pre></body></html>`;
                        } else {
                            htmlContent = `<!DOCTYPE html><html><head><meta charset="utf-8">
                                <style>body { font-family: system-ui; padding: 24px; line-height: 1.8; white-space: pre-wrap; }</style>
                            </head><body>${this.escapeHtml(result.content)}</body></html>`;
                        }
                        this.elements.reportFrame.srcdoc = htmlContent;
                    } else {
                        this.elements.reportFrame.srcdoc = `<div style="padding:20px;color:#e74c3c;">加载失败: ${result.error || '未知错误'}</div>`;
                    }
                })
                .catch(err => {
                    if (this.elements.reportFrame) {
                        this.elements.reportFrame.srcdoc = `<div style="padding:20px;color:#e74c3c;">网络错误: ${err.message}</div>`;
                    }
                });
        },
        
        /**
         * 【新增】更新路径面包屑
         */
        _updatePathBreadcrumb: function() {
            if (!this.elements.breadcrumb) return;
            
            if (!this.currentPath) {
                this.elements.breadcrumb.innerHTML = `<span style="cursor:pointer;color:#667eea;" onclick="ReportCenter.selectType('${this.currentType}')">${this.currentType}</span>`;
                return;
            }
            
            // 构建面包屑
            const parts = this.currentPath.split('/').filter(p => p);
            let html = `<span style="cursor:pointer;color:#667eea;" onclick="ReportCenter.selectType('${this.currentType}')">${this.currentType}</span>`;
            
            let accPath = '';
            for (let i = 0; i < parts.length; i++) {
                accPath += (accPath ? '/' : '') + parts[i];
                const isLast = i === parts.length - 1;
                if (isLast) {
                    html += ` <span style="color:#999;margin:0 4px;">›</span> <span>${parts[i]}</span>`;
                } else {
                    const pathForClick = accPath;
                    html += ` <span style="color:#999;margin:0 4px;">›</span> <span style="cursor:pointer;color:#667eea;" onclick="ReportCenter.openDirectory('${pathForClick}')">${parts[i]}</span>`;
                }
            }
            
            this.elements.breadcrumb.innerHTML = html;
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
            
            // Set iframe source based on file type
            const fileExt = filename.split('.').pop().toLowerCase();
            if (fileExt === 'pdf') {
                const pdfUrl = `/api/reports/file?type=${encodeURIComponent(type)}&filename=${encodeURIComponent(filename)}`;
                this.elements.reportFrame.src = pdfUrl;
            } else if (fileExt === 'epub') {
                // EPUB文件使用预览路由
                const previewUrl = `/api/reports/${encodeURIComponent(type)}/${encodeURIComponent(filename)}/preview?chapter=1`;
                this.elements.reportFrame.src = previewUrl;
            } else if (fileExt === 'html' || fileExt === 'htm') {
                // HTML文件直接在iframe中加载
                const htmlUrl = `/api/reports/file?type=${encodeURIComponent(type)}&filename=${encodeURIComponent(filename)}`;
                this.elements.reportFrame.src = htmlUrl;
            } else {
                this.elements.reportFrame.srcdoc = '<html><body style="display:flex;justify-content:center;align-items:center;height:100vh;"><p>不支持的文件格式</p></body></html>';
            }
            
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
            this.elements.reportViewer.style.display = '';  // 清除可能残留的内联样式
            this.elements.reportFrame.src = '';
            this.elements.reportFrame.srcdoc = '';  // 清除 srcdoc 内容
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
                        this.renderSearchResults(result.data.reports, keyword);
                        this.updateBreadcrumb('搜索: ' + keyword + ' (' + result.data.total + '个结果)');
                    }
                })
                .catch(error => {
                    this.showLoading(false);
                    console.error('Error searching:', error);
                });
        },

        /**
         * Render search results grouped by directory
         */
        renderSearchResults: function(reports, keyword) {
            const listEl = this.elements.reportList;
            if (!listEl) return;

            if (!reports || reports.length === 0) {
                listEl.innerHTML = '<div style="text-align:center;padding:40px;color:#999;">未找到匹配文件</div>';
                return;
            }

            // 按 display_path 分组
            const groups = {};
            reports.forEach(r => {
                const groupKey = r.display_path || r.type_name || r.type;
                if (!groups[groupKey]) {
                    groups[groupKey] = { path: groupKey, type: r.type, parent_path: r.parent_path, files: [] };
                }
                groups[groupKey].files.push(r);
            });

            let html = '';
            Object.values(groups).forEach(group => {
                // 目录标题（可点击导航）
                const navPath = group.parent_path ? `${group.type}/${group.parent_path}` : group.type;
                html += `<div style="padding:8px 12px;background:#f5f5f5;border-bottom:1px solid #e0e0e0;font-size:13px;font-weight:500;color:#555;cursor:pointer;" 
                    onclick="ReportCenter.openDirectory('${navPath.replace(/'/g, "\\'")}')">
                    📁 ${group.path}
                </div>`;

                // 文件列表
                group.files.forEach(report => {
                    const nameHighlighted = report.filename.replace(
                        new RegExp('(' + keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'),
                        '<span style="background:#fff3cd;font-weight:bold;">$1</span>'
                    );
                    html += `<div class="report-item" style="padding:10px 12px 10px 28px;border-bottom:1px solid #eee;cursor:pointer;transition:background 0.2s;"
                        onmouseover="this.style.background='#f8f8f8'" onmouseout="this.style.background=''"
                        onclick="ReportCenter.openDocInline('${(report.type + '/' + report.relative_path).replace(/'/g, "\\'")}', '${report.name.replace(/'/g, "\\'")}')">
                        <span style="margin-right:6px;">${report.format_icon}</span>
                        <span>${nameHighlighted}</span>
                        <span style="float:right;font-size:11px;color:#999;">${report.size_formatted} · ${report.modified_time_formatted}</span>
                    </div>`;
                });
            });

            listEl.innerHTML = html;
        },
        
        /**
         * Update breadcrumb
         */
        updateBreadcrumb: function(text) {
            if (this.elements.breadcrumb) {
                this.elements.breadcrumb.textContent = text;
                // 路径面包屑会在 _updatePathBreadcrumb 中更新
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
