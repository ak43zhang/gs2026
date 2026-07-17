# 三个问题深度分析与解决方案

## 问题1: 语音保存在哪里

### 现状
- **缓存目录**: `F:\pyworkspace2026\gs2026\data\tts_cache`
- **文件命名**: `{text_hash}_{voice}.mp3`
- **元数据**: `{text_hash}_{voice}.json`

### 问题
目录刚创建，为空，所有音频需要实时生成

### 解决方案
1. **预生成所有音频**（推荐）
2. **边播放边生成**（当前实现，但有延迟）

---

## 问题2: 如何确定是否预生成所有音频

### 现状
```
总段数: 943
已就绪: 125 (13.3%)
未就绪: 818 (86.7%)
```

### 根本原因
`generate_for_segments` 只检查缓存，不主动生成

### 解决方案

**方案A: 添加预生成API（推荐）**

后端修改 (`tts_service.py`):
```python
def pregenerate_all(self, segments, voice, speed):
    """预生成所有音频"""
    for i, segment in enumerate(segments):
        text = segment['text']
        if not self.is_cached(text, voice):
            self.generate(text, voice, speed)
        # 每10个报告一次进度
        if i % 10 == 0:
            print(f"Generated {i}/{len(segments)}")
```

前端添加"预生成"按钮:
```html
<button id="pregenerate-btn">预生成所有语音</button>
```

**方案B: 播放时显示生成进度**
- 当前段生成时显示"生成语音中..."
- 生成完成后自动播放

---

## 问题3: 为什么第2段被跳过

### 分析结果
- 后端测试显示第2段**有音频信息**
- MD5匹配**正常**
- 但**音频文件实际不存在**

### 根本原因
1. `prepareTTS` 标记 `ready: True`（基于缓存检查）
2. 但实际音频文件**未生成**
3. 播放时实时生成**可能失败或延迟**

### 解决方案

**修复1: 修正ready状态判断**
```python
# tts_service.py
def generate_for_segments(self, segments, voice, speed):
    for segment in segments:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        audio_path = self.get_audio_path(text, voice)
        
        # 检查文件实际存在
        ready = audio_path.exists() and audio_path.stat().st_size > 0
        
        results[text_hash] = {
            "ready": ready,  # 基于文件实际存在
            ...
        }
```

**修复2: 前端播放时强制生成**
```javascript
// report-page.js
playCurrent: function() {
    const seg = this.segments[this.currentSegment];
    
    // 显示生成中
    this.showSegmentStatus(this.currentSegment, 'generating');
    
    // 强制生成
    fetch('/api/reports/tts/generate', {...})
        .then(() => {
            // 等待文件写入
            setTimeout(() => this.playAudio(), 500);
        });
}
```

**修复3: 添加段落级状态显示**
```javascript
// 每个段落显示状态
[1] 第一部分：市场概况... [○]  // 未生成
[2] 其中，非ST股...     [⏳]  // 生成中
[3] 涨停原因...         [✓]  // 已就绪
```

---

## 立即实施方案

### 步骤1: 修复ready状态判断
修改 `tts_service.py` 中的 `generate_for_segments`

### 步骤2: 添加段落级状态显示
修改前端，显示每个段落的生成状态

### 步骤3: 播放时强制生成
确保播放前音频已生成

### 步骤4: 添加预生成按钮（可选）
让用户可以选择预生成所有音频

---

## 代码修改

### 修改1: tts_service.py
```python
def generate_for_segments(self, segments, voice, speed):
    ...
    for segment in segments:
        ...
        # 检查文件实际存在且非空
        audio_path = self.get_audio_path(text, voice)
        ready = audio_path.exists() and audio_path.stat().st_size > 1024
        
        results[text_hash] = {
            "text_hash": text_hash,
            "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
            "duration": info.get("duration", 0) if ready else 0,
            "ready": ready  # 基于文件实际存在
        }
```

### 修改2: report-page.js
```javascript
// 添加段落状态显示
renderSegments: function() {
    this.segments.forEach((seg, idx) => {
        const status = seg.ready ? '✓' : (seg.generating ? '⏳' : '○');
        // 渲染状态图标
    });
}

// 播放时强制生成
playCurrent: function() {
    const seg = this.segments[this.currentSegment];
    
    if (!seg.ready) {
        // 显示生成中
        this.showSegmentStatus(this.currentSegment, 'generating');
        
        // 强制生成
        fetch('/api/reports/tts/generate', {...})
            .then(() => {
                seg.ready = true;
                this.playAudio();
            });
    } else {
        this.playAudio();
    }
}
```

---

## 验证方法

1. **清除缓存**: 删除 `data/tts_cache` 目录
2. **打开报告**: 观察段落状态（应该都是○）
3. **点击播放**: 观察当前段变为⏳，然后变为✓
4. **检查音频**: 确认 `data/tts_cache` 有文件生成
