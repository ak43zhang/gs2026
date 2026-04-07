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
        segmentStrategy: localStorage.getItem('tts_strategy') || 'original', // 默认按句分割
        
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
            const self = this;
            
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
                        
                        self.segments.forEach((seg, idx) => {
                            const textHash = self._getTextHash(seg.text);
                            const audioInfo = hashMap[textHash];
                            
                            if (audioInfo) {
                                seg.audio_url = audioInfo.audio_url;
                                seg.duration = audioInfo.duration;
                                seg.ready = audioInfo.ready;
                                matchCount++;
                            } else {
                                // 如果后端没有匹配到，生成一个URL（播放时会实时生成）
                                seg.audio_url = '/api/reports/tts/audio?text=' + textHash + '&voice=' + voice;
                                seg.ready = false;
                            }
                        });
                        
                        console.log('TTS prepared: ' + matchCount + '/' + self.segments.length + ' segments matched');
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
         * MD5 hash function (JavaScript implementation)
         */
        _md5: function(string) {
            // MD5 implementation
            function rotateLeft(lValue, iShiftBits) {
                return (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits));
            }
            
            function addUnsigned(lX, lY) {
                var lX4, lY4, lX8, lY8, lResult;
                lX8 = (lX & 0x80000000);
                lY8 = (lY & 0x80000000);
                lX4 = (lX & 0x40000000);
                lY4 = (lY & 0x40000000);
                lResult = (lX & 0x3FFFFFFF) + (lY & 0x3FFFFFFF);
                if (lX4 & lY4) return (lResult ^ 0x80000000 ^ lX8 ^ lY8);
                if (lX4 | lY4) {
                    if (lResult & 0x40000000) return (lResult ^ 0xC0000000 ^ lX8 ^ lY8);
                    else return (lResult ^ 0x40000000 ^ lX8 ^ lY8);
                } else {
                    return (lResult ^ lX8 ^ lY8);
                }
            }
            
            function f(x, y, z) { return (x & y) | ((~x) & z); }
            function g(x, y, z) { return (x & z) | (y & (~z)); }
            function h(x, y, z) { return (x ^ y ^ z); }
            function i(x, y, z) { return (y ^ (x | (~z))); }
            
            function ff(a, b, c, d, x, s, ac) {
                a = addUnsigned(a, addUnsigned(addUnsigned(f(b, c, d), x), ac));
                return addUnsigned(rotateLeft(a, s), b);
            }
            
            function gg(a, b, c, d, x, s, ac) {
                a = addUnsigned(a, addUnsigned(addUnsigned(g(b, c, d), x), ac));
                return addUnsigned(rotateLeft(a, s), b);
            }
            
            function hh(a, b, c, d, x, s, ac) {
                a = addUnsigned(a, addUnsigned(addUnsigned(h(b, c, d), x), ac));
                return addUnsigned(rotateLeft(a, s), b);
            }
            
            function ii(a, b, c, d, x, s, ac) {
                a = addUnsigned(a, addUnsigned(addUnsigned(i(b, c, d), x), ac));
                return addUnsigned(rotateLeft(a, s), b);
            }
            
            function convertToWordArray(string) {
                var lWordCount;
                var lMessageLength = string.length;
                var lNumberOfWordsTemp1 = lMessageLength + 8;
                var lNumberOfWordsTemp2 = (lNumberOfWordsTemp1 - (lNumberOfWordsTemp1 % 64)) / 64;
                var lNumberOfWords = (lNumberOfWordsTemp2 + 1) * 16;
                var lWordArray = new Array(lNumberOfWords - 1);
                var lBytePosition = 0;
                var lByteCount = 0;
                while (lByteCount < lMessageLength) {
                    lWordCount = (lByteCount - (lByteCount % 4)) / 4;
                    lBytePosition = (lByteCount % 4) * 8;
                    lWordArray[lWordCount] = (lWordArray[lWordCount] | (string.charCodeAt(lByteCount) << lBytePosition));
                    lByteCount++;
                }
                lWordCount = (lByteCount - (lByteCount % 4)) / 4;
                lBytePosition = (lByteCount % 4) * 8;
                lWordArray[lWordCount] = lWordArray[lWordCount] | (0x80 << lBytePosition);
                lWordArray[lNumberOfWords - 2] = lMessageLength << 3;
                lWordArray[lNumberOfWords - 1] = lMessageLength >>> 29;
                return lWordArray;
            }
            
            function wordToHex(lValue) {
                var wordToHexValue = "", wordToHexValueTemp = "", lByte, lCount;
                for (lCount = 0; lCount <= 3; lCount++) {
                    lByte = (lValue >>> (lCount * 8)) & 255;
                    wordToHexValueTemp = "0" + lByte.toString(16);
                    wordToHexValue = wordToHexValue + wordToHexValueTemp.substr(wordToHexValueTemp.length - 2, 2);
                }
                return wordToHexValue;
            }
            
            var x = [];
            var k, AA, BB, CC, DD, a, b, c, d;
            var S11 = 7, S12 = 12, S13 = 17, S14 = 22;
            var S21 = 5, S22 = 9, S23 = 14, S24 = 20;
            var S31 = 4, S32 = 11, S33 = 16, S34 = 23;
            var S41 = 6, S42 = 10, S43 = 15, S44 = 21;
            
            string = unescape(encodeURIComponent(string));
            x = convertToWordArray(string);
            a = 0x67452301; b = 0xEFCDAB89; c = 0x98BADCFE; d = 0x10325476;
            
            for (k = 0; k < x.length; k += 16) {
                AA = a; BB = b; CC = c; DD = d;
                a = ff(a, b, c, d, x[k + 0], S11, 0xD76AA478);
                d = ff(d, a, b, c, x[k + 1], S12, 0xE8C7B756);
                c = ff(c, d, a, b, x[k + 2], S13, 0x242070DB);
                b = ff(b, c, d, a, x[k + 3], S14, 0xC1BDCEEE);
                a = ff(a, b, c, d, x[k + 4], S11, 0xF57C0FAF);
                d = ff(d, a, b, c, x[k + 5], S12, 0x4787C62A);
                c = ff(c, d, a, b, x[k + 6], S13, 0xA8304613);
                b = ff(b, c, d, a, x[k + 7], S14, 0xFD469501);
                a = ff(a, b, c, d, x[k + 8], S11, 0x698098D8);
                d = ff(d, a, b, c, x[k + 9], S12, 0x8B44F7AF);
                c = ff(c, d, a, b, x[k + 10], S13, 0xFFFF5BB1);
                b = ff(b, c, d, a, x[k + 11], S14, 0x895CD7BE);
                a = ff(a, b, c, d, x[k + 12], S11, 0x6B901122);
                d = ff(d, a, b, c, x[k + 13], S12, 0xFD987193);
                c = ff(c, d, a, b, x[k + 14], S13, 0xA679438E);
                b = ff(b, c, d, a, x[k + 15], S14, 0x49B40821);
                a = gg(a, b, c, d, x[k + 1], S21, 0xF61E2562);
                d = gg(d, a, b, c, x[k + 6], S22, 0xC040B340);
                c = gg(c, d, a, b, x[k + 11], S23, 0x265E5A51);
                b = gg(b, c, d, a, x[k + 0], S24, 0xE9B6C7AA);
                a = gg(a, b, c, d, x[k + 5], S21, 0xD62F105D);
                d = gg(d, a, b, c, x[k + 10], S22, 0x2441453);
                c = gg(c, d, a, b, x[k + 15], S23, 0xD8A1E681);
                b = gg(b, c, d, a, x[k + 4], S24, 0xE7D3FBC8);
                a = gg(a, b, c, d, x[k + 9], S21, 0x21E1CDE6);
                d = gg(d, a, b, c, x[k + 14], S22, 0xC33707D6);
                c = gg(c, d, a, b, x[k + 3], S23, 0xF4D50D87);
                b = gg(b, c, d, a, x[k + 8], S24, 0x455A14ED);
                a = gg(a, b, c, d, x[k + 13], S21, 0xA9E3E905);
                d = gg(d, a, b, c, x[k + 2], S22, 0xFCEFA3F8);
                c = gg(c, d, a, b, x[k + 7], S23, 0x676F02D9);
                b = gg(b, c, d, a, x[k + 12], S24, 0x8D2A4C8A);
                a = hh(a, b, c, d, x[k + 5], S31, 0xFFFA3942);
                d = hh(d, a, b, c, x[k + 8], S32, 0x8771F681);
                c = hh(c, d, a, b, x[k + 11], S33, 0x6D9D6122);
                b = hh(b, c, d, a, x[k + 14], S34, 0xFDE5380C);
                a = hh(a, b, c, d, x[k + 1], S31, 0xA4BEEA44);
                d = hh(d, a, b, c, x[k + 4], S32, 0x4BDECFA9);
                c = hh(c, d, a, b, x[k + 7], S33, 0xF6BB4B60);
                b = hh(b, c, d, a, x[k + 10], S34, 0xBEBFBC70);
                a = hh(a, b, c, d, x[k + 13], S31, 0x289B7EC6);
                d = hh(d, a, b, c, x[k + 0], S32, 0xEAA127FA);
                c = hh(c, d, a, b, x[k + 3], S33, 0xD4EF3085);
                b = hh(b, c, d, a, x[k + 6], S34, 0x4881D05);
                a = hh(a, b, c, d, x[k + 9], S31, 0xD9D4D039);
                d = hh(d, a, b, c, x[k + 12], S32, 0xE6DB99E5);
                c = hh(c, d, a, b, x[k + 15], S33, 0x1FA27CF8);
                b = hh(b, c, d, a, x[k + 2], S34, 0xC4AC5665);
                a = ii(a, b, c, d, x[k + 0], S41, 0xF4292244);
                d = ii(d, a, b, c, x[k + 7], S42, 0x432AFF97);
                c = ii(c, d, a, b, x[k + 14], S43, 0xAB9423A7);
                b = ii(b, c, d, a, x[k + 5], S44, 0xFC93A039);
                a = ii(a, b, c, d, x[k + 12], S41, 0x655B59C3);
                d = ii(d, a, b, c, x[k + 3], S42, 0x8F0CCC92);
                c = ii(c, d, a, b, x[k + 10], S43, 0xFFEFF47D);
                b = ii(b, c, d, a, x[k + 1], S44, 0x85845DD1);
                a = ii(a, b, c, d, x[k + 8], S41, 0x6FA87E4F);
                d = ii(d, a, b, c, x[k + 15], S42, 0xFE2CE6E0);
                c = ii(c, d, a, b, x[k + 6], S43, 0xA3014314);
                b = ii(b, c, d, a, x[k + 13], S44, 0x4E0811A1);
                a = ii(a, b, c, d, x[k + 4], S41, 0xF7537E82);
                d = ii(d, a, b, c, x[k + 11], S42, 0xBD3AF235);
                c = ii(c, d, a, b, x[k + 2], S43, 0x2AD7D2BB);
                b = ii(b, c, d, a, x[k + 9], S44, 0xEB86D391);
                a = addUnsigned(a, AA);
                b = addUnsigned(b, BB);
                c = addUnsigned(c, CC);
                d = addUnsigned(d, DD);
            }
            
            var tempValue = wordToHex(a) + wordToHex(b) + wordToHex(c) + wordToHex(d);
            return tempValue.toLowerCase();
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
