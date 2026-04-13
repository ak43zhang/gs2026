# TTS阅读"隔一个读一个"问题详细分析报告

## 问题描述

点击阅读时，编号1读完后直接跳过编号2开始读编号3，每次都是隔一个读一个。

## 根本原因分析

### 1. 问题定位

经过详细排查，发现问题出在 **前端 `prepareTTS` 方法的索引匹配逻辑**。

### 2. 代码分析

**前端代码 (`report-page.js`):**

```javascript
// prepareTTS 方法
result.data.segments.forEach((seg, idx) => {
    if (this.segments[idx]) {
        this.segments[idx].audio_url = seg.audio_url;
        this.segments[idx].duration = seg.duration;
    }
});

// playCurrent 方法
playCurrent: function() {
    const seg = this.segments[this.currentSegment];
    if (!seg.audio_url || !this.audio) return;  // <-- 问题在这里！
    // ...
}
```

**后端代码 (`tts_service.py`):**

```python
def generate_for_segments(self, segments, voice, speed):
    results = []
    for seg in segments:
        # 生成音频...
        results.append({
            'text_hash': text_hash,
            'audio_url': f'/api/reports/tts/audio?text={text_hash}&voice={voice}',
            'duration': duration
        })
    return results
```

### 3. 问题机制

**假设情况：**
- 前端使用 `original` 策略，提取了 10 段
- 后端 `prepare_tts` 使用 `smart` 策略，提取了 8 段

**匹配过程：**

| 索引 | 前端段落 (original) | 后端段落 (smart) | 匹配结果 |
|------|---------------------|------------------|----------|
| 0 | 段0 | 段0 | ✅ 匹配 |
| 1 | 段1 | 段1 | ✅ 匹配 |
| 2 | 段2 | - | ❌ 后端无此段，audio_url为undefined |
| 3 | 段3 | 段2 | ⚠️ 错位！段3拿到了段2的音频 |
| 4 | 段4 | 段3 | ⚠️ 错位！ |
| ... | ... | ... | ... |

**播放过程：**

1. 播放段0 ✅
2. 播放段1 ✅
3. 播放段2 ❌ `audio_url` 为 undefined，直接 return，用户感知为"跳过"
4. 播放段3 ✅（但播放的是段2的内容！）

### 4. 为什么之前修复没解决？

之前的修复（commit 17b532e）确实添加了 `strategy` 参数，但可能存在以下问题：

1. **缓存问题**：`pdf_reader.extract_and_cache` 使用文件路径+策略作为缓存key，但如果缓存文件已存在且策略不同，可能返回错误的缓存
2. **策略传递问题**：前端 `loadContent` 和 `prepareTTS` 调用的时机不同，策略可能不一致
3. **后端默认策略**：如果 `prepare_tts` 接口的 `strategy` 参数解析失败，会回退到 'smart'

## 完整修复方案

### 方案1: 使用文本哈希匹配（推荐）

不依赖索引，而是使用文本内容的哈希值来匹配前后端段落。

**后端修改 (`tts_service.py`):**

```python
def generate_for_segments(self, segments, voice, speed):
    results = {}
    for seg in segments:
        text = seg['text']
        text_hash = self._get_text_hash(text)
        
        # 生成音频...
        audio_path = self._generate_audio(text, voice, speed)
        duration = self._get_audio_duration(audio_path)
        
        # 使用文本哈希作为key
        results[text_hash] = {
            'text_hash': text_hash,
            'audio_url': f'/api/reports/tts/audio?text={text_hash}&voice={voice}',
            'duration': duration
        }
    
    return results  # 返回dict而不是list
```

**前端修改 (`report-page.js`):**

```javascript
// prepareTTS
result.data.segments.forEach((seg, idx) => {
    // 使用文本哈希匹配而不是索引
    const textHash = self._getTextHash(seg.text);
    const targetSeg = this.segments.find(s => s.text_hash === textHash);
    if (targetSeg) {
        targetSeg.audio_url = seg.audio_url;
        targetSeg.duration = seg.duration;
    }
});

// 辅助方法：计算文本哈希
_getTextHash: function(text) {
    // 简单的哈希算法
    let hash = 0;
    for (let i = 0; i < text.length; i++) {
        const char = text.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash.toString(16);
}
```

### 方案2: 强制清除缓存并重新提取

确保前后端使用完全相同的提取结果。

**后端修改 (`report.py`):**

```python
@report_bp.route('/<report_type>/<filename>/tts/prepare', methods=['POST'])
def prepare_tts(report_type, filename):
    # ...
    strategy = data.get('strategy', 'smart')
    
    # 强制重新提取，不使用缓存
    segments = pdf_reader.extract_text(file_path, strategy)  # 不使用 extract_and_cache
    
    # ...
```

**前端修改：**

在切换策略时清除缓存：

```javascript
changeStrategy: function(strategy) {
    this.segmentStrategy = strategy;
    localStorage.setItem('tts_strategy', strategy);
    
    // 清除当前报告的缓存
    if (this.currentReport) {
        this.clearCache(this.currentReport.type, this.currentReport.filename);
    }
    
    // 重新加载
    if (this.currentReport) {
        this.loadContent(this.currentReport.type, this.currentReport.filename);
    }
}
```

### 方案3: 统一使用前端分段结果

后端不再重新提取文本，而是直接使用前端传来的分段结果。

**后端修改 (`report.py`):**

```python
@report_bp.route('/<report_type>/<filename>/tts/prepare', methods=['POST'])
def prepare_tts(report_type, filename):
    # ...
    
    # 接收前端传来的segments
    frontend_segments = data.get('segments', [])
    
    if frontend_segments:
        # 使用前端的分段结果
        segments = frontend_segments
    else:
        # 回退到后端提取
        strategy = data.get('strategy', 'smart')
        segments = pdf_reader.extract_text(file_path, strategy)
    
    # ...
```

**前端修改：**

```javascript
prepareTTS: function() {
    // ...
    body: JSON.stringify({
        voice: voice,
        speed: speed,
        strategy: strategy,
        segments: this.segments  // 传递前端的分段结果
    })
}
```

## 推荐方案

**推荐方案1（文本哈希匹配）**，原因：
1. 不依赖索引，即使前后端分段数量不同也能正确匹配
2. 兼容性好，不需要修改缓存机制
3. 可以处理部分段落匹配的情况

## 实施步骤

1. 修改 `tts_service.py` 的 `generate_for_segments` 方法，返回 dict
2. 修改 `report.py` 的 `prepare_tts` 接口，返回文本哈希映射
3. 修改前端 `report-page.js`，使用文本哈希匹配
4. 添加 `_getTextHash` 辅助方法
5. 测试验证

## 验证方法

1. 使用 `ZTB_Report_20260403_TTS.pdf` 测试
2. 切换不同策略（original/line/smart）
3. 检查每段是否都有正确的 `audio_url`
4. 播放测试，确保没有跳过

---

**分析时间：** 2026-04-07  
**分析人：** AI Assistant
