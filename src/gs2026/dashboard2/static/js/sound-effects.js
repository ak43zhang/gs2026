/**
 * sound-effects.js —— 全站统一音效模块（可复用）
 *
 * 遵循《docs/20-开发规范/音效开发统一规范.md》前端方式（方案A）：
 *   文件驱动 + 配置化 + 全局开关(持久化) + 失败降级(Web Audio 蜂鸣) + 异常隔离。
 *
 * 设计目标：任何页面 <script src=".../sound-effects.js"> 引入即用，
 *          新增音效只改 SoundFX.register(...)，新增"集合从无到有/新成员"检测
 *          只需 new SoundFX.NewMemberDetector(...)。无需复制粘贴逻辑。
 *
 * 用法示例：
 *   SoundFX.register('zhongla', '/static/sounds/zhongla.mp3');
 *   const det = new SoundFX.NewMemberDetector({ sound: 'zhongla', enabledKey: 'intersect_sound_enabled' });
 *   // 每次结果刷新：
 *   det.check(stockResult.map(s => s.code));   // 出现新成员则自动播放
 *   det.reset();                               // 关闭功能时清空基线
 *   SoundFX.isEnabled('intersect_sound_enabled');    // 读开关
 *   SoundFX.toggle('intersect_sound_enabled');       // 切开关(持久化)
 */
(function (global) {
    'use strict';

    var _files = {};       // type -> url
    var _cache = {};       // type -> HTMLAudioElement（预加载缓存）

    /** 注册一个音效：type 语义名 -> mp3 url。重复注册以最后一次为准。 */
    function register(type, url) {
        _files[type] = url;
        // 预加载，避免首次播放卡顿；失败不抛
        try {
            var a = new Audio(url);
            a.preload = 'auto';
            _cache[type] = a;
        } catch (e) { /* ignore */ }
        return SoundFX;
    }

    function _getAudio(type) {
        if (_cache[type]) return _cache[type];
        var url = _files[type];
        if (!url) return null;
        try { _cache[type] = new Audio(url); return _cache[type]; }
        catch (e) { return null; }
    }

    /** 全局开关读取（localStorage 持久化，默认开启） */
    function isEnabled(enabledKey) {
        if (!enabledKey) return true;
        return localStorage.getItem(enabledKey) !== 'false';
    }

    /** 切换开关并持久化，返回切换后的状态 */
    function toggle(enabledKey) {
        var next = !isEnabled(enabledKey);
        localStorage.setItem(enabledKey, next ? 'true' : 'false');
        return next;
    }

    function setEnabled(enabledKey, val) {
        localStorage.setItem(enabledKey, val ? 'true' : 'false');
    }

    /** 降级蜂鸣（Web Audio 合成音，不依赖文件） */
    function _fallbackBeep() {
        try {
            var Ctx = global.AudioContext || global.webkitAudioContext;
            if (!Ctx) return;
            var ctx = new Ctx();
            var osc = ctx.createOscillator(), gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.frequency.value = 700; osc.type = 'sine';
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
            osc.start(); osc.stop(ctx.currentTime + 0.3);
        } catch (e) { /* ignore */ }
    }

    /**
     * 统一播放入口。
     * @param {string} type      已 register 的音效名
     * @param {string} [enabledKey]  开关的 localStorage 键；关闭则不播
     */
    function play(type, enabledKey) {
        if (enabledKey && !isEnabled(enabledKey)) return;
        try {
            var a = _getAudio(type);
            if (a) {
                a.currentTime = 0;                 // 重置以支持连续触发
                var p = a.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(function (err) {
                        console.warn('[SoundFX] play blocked/fail -> beep', err);
                        _fallbackBeep();
                    });
                }
            } else {
                _fallbackBeep();
            }
        } catch (e) {
            console.warn('[SoundFX]', e);
            _fallbackBeep();
        }
    }

    /**
     * 通用「集合出现新成员」检测器（从无到有 / 新增成员 / 换成员 都会触发）。
     * 判定：本次集合 − 上次集合 ≠ ∅（存在上次没有的元素）即触发。
     *
     * @param {object} opts
     *   opts.sound       播放的音效 type
     *   opts.enabledKey  开关 localStorage 键（可选）
     *   opts.getEnabled  额外的开启判断函数（可选，如"仅交集模式开启时才检测"）
     */
    function NewMemberDetector(opts) {
        opts = opts || {};
        this.sound = opts.sound;
        this.enabledKey = opts.enabledKey || null;
        this.getEnabled = typeof opts.getEnabled === 'function' ? opts.getEnabled : null;
        this._prev = new Set();
    }

    /**
     * 传入本次结果的 id 列表；若出现上次没有的新成员则播放音效。
     * @param {Array} ids  本次成员标识数组（会转 String 去重）
     * @returns {boolean}  是否触发了播放
     */
    NewMemberDetector.prototype.check = function (ids) {
        var cur = new Set((ids || []).map(function (x) { return String(x); }));
        var gate = this.getEnabled ? !!this.getEnabled() : true;
        var hasNew = false;
        if (gate) {
            for (var v of cur) {
                if (!this._prev.has(v)) { hasNew = true; break; }
            }
            if (hasNew) play(this.sound, this.enabledKey);
        }
        this._prev = cur;   // 更新基线
        return gate && hasNew;
    };

    /** 清空基线（关闭功能时调用，下次重新按"从无到有"判定） */
    NewMemberDetector.prototype.reset = function () {
        this._prev = new Set();
    };

    var SoundFX = {
        register: register,
        play: play,
        isEnabled: isEnabled,
        toggle: toggle,
        setEnabled: setEnabled,
        NewMemberDetector: NewMemberDetector
    };

    global.SoundFX = SoundFX;
})(window);
