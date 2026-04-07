/**
 * Report Center Page
 * File system based report management
 * Version: 20250407-2 (force cache refresh)
 */

(function() {
    'use strict';
    
    // Force clear cache on version change
    const CURRENT_VERSION = '20250407-2';
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
            
            // Jump to segment
            if (this.elements.jumpBtn && this.elements.jumpInput) {
                this.elements.jumpBtn.addEventListener('click', () => this.handleJump());
                this.elements.jumpInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this.handleJump();
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
        
        /**
         * Handle jump to segment
         */
        handleJump: function() {
            if (!this.elements.jumpInput) return;
            
            const inputValue = this.elements.jumpInput.value.trim();
            const targetIndex = parseInt(inputValue) - 1; // Convert to 0-based
            
            if (isNaN(targetIndex) || targetIndex < 0 || targetIndex >= this.segments.length) {
                alert('请输入有效的段号 (1-' + this.segments.length + ')');
                return;
            }
            
            const autoPlay = this.elements.jumpAutoPlay ? this.elements.jumpAutoPlay.checked : true;
            
            // Jump to target segment
            this.goTo(targetIndex);
            
            // Auto play if checked
            if (autoPlay && !this.isPlaying) {
                this.play();
            }
            
            // Clear input
            this.elements.jumpInput.value = '';
            
            console.log('Jumped to segment ' + (targetIndex + 1));
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
                        // 使用文本哈希匹配，而不是索引匹配
                        const hashMap = result.data.segments;  // {text_hash: {audio_url, duration, ready}}
                        let matchCount = 0;
                        const total = self.segments.length;
                        
                        // Try hash matching with progress
                        self.segments.forEach((seg, idx) => {
                            const textHash = self._getTextHash(seg.text);
                            const audioInfo = hashMap[textHash];
                            
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
                        
                        // Hide loading progress
                        setTimeout(() => {
                            self.hideLoadingProgress();
                        }, 500);
                        
                        console.log('TTS prepared: ' + matchCount + '/' + self.segments.length + ' segments matched by hash');
                        
                        // Fallback: if hash match rate is low, use index matching
                        if (matchCount < self.segments.length * 0.5) {
                            console.warn('WARNING: Low hash match rate (' + matchCount + '/' + self.segments.length + '), falling back to index matching');
                            
                            // Convert hashMap to array (backend returns segments in order)
                            const audioArray = Object.values(hashMap);
                            
                            self.segments.forEach((seg, idx) => {
                                if (audioArray[idx]) {
                                    seg.audio_url = audioArray[idx].audio_url;
                                    seg.duration = audioArray[idx].duration;
                                    seg.ready = audioArray[idx].ready;
                                } else if (!seg.audio_url) {
                                    // Still no audio, generate URL
                                    const textHash = self._getTextHash(seg.text);
                                    seg.audio_url = '/api/reports/tts/audio?text=' + textHash + '&voice=' + voice;
                                    seg.ready = false;
                                }
                            });
                            
                            console.log('Fallback index matching applied');
                        }
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
            if (!this.audio) return;
            
            // 如果没有audio_url，生成一个
            if (!seg.audio_url) {
                const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
                const textHash = this._getTextHash(seg.text);
                seg.audio_url = '/api/reports/tts/audio?text=' + textHash + '&voice=' + voice;
            }
            
            // Show loading
            if (this.elements.playBtn) {
                this.elements.playBtn.innerHTML = '&#9203;';
                this.elements.playBtn.disabled = true;
            }
            
            // First, ensure audio is generated
            const voice = this.elements.voiceSelect ? this.elements.voiceSelect.value : 'xiaoxiao';
            const speed = this.elements.speedSelect ? parseFloat(this.elements.speedSelect.value) : 1.0;
            const self = this;
            
            // Function to try playing audio with retry
            const tryPlayAudio = function(retryCount) {
                if (retryCount <= 0) {
                    console.error('Failed to load audio after retries');
                    if (self.elements.playBtn) {
                        self.elements.playBtn.innerHTML = '&#9654;';
                        self.elements.playBtn.disabled = false;
                    }
                    return;
                }
                
                self.audio.src = seg.audio_url;
                self.audio.load();
                
                self.audio.play().then(() => {
                    // Success
                    if (self.elements.playBtn) {
                        self.elements.playBtn.innerHTML = '&#9654;';
                        self.elements.playBtn.disabled = false;
                    }
                }).catch(err => {
                    console.warn('Play failed, retrying... (' + retryCount + ' left)');
                    // Wait a bit and retry
                    setTimeout(function() {
                        tryPlayAudio(retryCount - 1);
                    }, 500);
                });
            };
            
            // Generate audio first
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
                        // Audio generated, wait a bit for file to be written then play
                        setTimeout(function() {
                            tryPlayAudio(5); // Try up to 5 times
                        }, 200);
                    } else {
                        console.error('TTS generation failed:', result.error);
                        if (self.elements.playBtn) {
                            self.elements.playBtn.innerHTML = '&#9654;';
                            self.elements.playBtn.disabled = false;
                        }
                    }
                })
                .catch(error => {
                    console.error('Error generating TTS:', error);
                    if (self.elements.playBtn) {
                        self.elements.playBtn.innerHTML = '&#9654;';
                        self.elements.playBtn.disabled = false;
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
