# PDF TTS 阅读优化设计方案

## 版本信息
- 设计日期：2026-04-07
- 设计版本：v1.0
- 状态：已确认，实施中

## 设计目标
实现人声流畅完整的PDF报告TTS阅读体验，像真人朗读一样自然。

## 核心架构：三层智能分段系统

```
PDF文本
    ↓
【第一层：结构识别】
- 识别标题（字体大小、位置、格式）
- 识别段落（缩进、间距）
- 识别列表（序号、项目符号）
- 过滤噪声（页眉页脚、页码）
    ↓
【第二层：语义分段】
- 短句合并（<15字的句子合并到前一句）
- 长句分割（>60字的句子按逗号分割）
- 段落合并（空行分隔的短段落合并）
    ↓
【第三层：朗读优化】
- 添加停顿标记（逗号0.3秒，句号0.8秒，段落2秒）
- 数字格式化（2026-04-07 → 2026年4月7日）
- 特殊符号处理（%、℃、￥等）
- 预加载机制（提前生成后续3段音频）
    ↓
TTS音频流
```

## 详细设计

### 1. 智能分段算法

```python
def smart_segment(text: str, strategy: str = "smart") -> List[Dict]:
    """
    智能分段策略
    
    Args:
        text: 原始文本
        strategy: 分段策略
            - "original": 原始按句子分割（保留兼容）
            - "line": 按行分割
            - "smart": 智能分段（推荐）
    """
    if strategy == "original":
        return split_by_sentences(text)
    elif strategy == "line":
        return split_by_lines(text)
    else:  # smart
        return split_smart(text)

def split_smart(text: str) -> List[Dict]:
    """智能分段：合并短句，分割长句，保持语义完整"""
    # Step 1: 基础分句
    raw_sentences = split_by_punctuation(text)
    
    # Step 2: 短句合并（避免碎片化）
    segments = []
    buffer = ""
    
    for sent in raw_sentences:
        if len(sent) < 15:  # 短句，累积到buffer
            buffer += sent
        else:  # 长句，先输出buffer，再输出当前句
            if buffer:
                segments.append(buffer + sent)
                buffer = ""
            else:
                segments.append(sent)
    
    if buffer:  # 处理剩余buffer
        segments.append(buffer)
    
    # Step 3: 长句分割（避免一口气读完）
    final_segments = []
    for seg in segments:
        if len(seg) > 60:  # 超长句按逗号分割
            parts = split_by_comma(seg, max_len=50)
            final_segments.extend(parts)
        else:
            final_segments.append(seg)
    
    return final_segments
```

### 2. 停顿控制

```python
PAUSE_MARKS = {
    "，": 0.3,    # 逗号短停
    "；": 0.5,    # 分号稍长
    "。": 0.8,    # 句号停顿
    "！": 1.0,    # 感叹号
    "？": 1.0,    # 问号
    "\n": 1.2,    # 换行停顿
    "\n\n": 2.0,  # 段落停顿
}

def add_pause_marks(segments: List[str]) -> List[Dict]:
    """为每个segment添加停顿标记"""
    result = []
    for seg in segments:
        # 检测结尾标点，确定停顿时长
        pause = 0.8  # 默认
        for mark, duration in PAUSE_MARKS.items():
            if seg.endswith(mark.strip()):
                pause = duration
                break
        
        result.append({
            "text": seg,
            "pause_after": pause,
            "type": "sentence"
        })
    return result
```

### 3. 数字格式化

```python
NUMBER_PATTERNS = [
    # 日期
    (r"(\d{4})-(\d{2})-(\d{2})", r"\1年\2月\3日"),
    (r"(\d{4})/(\d{2})/(\d{2})", r"\1年\2月\3日"),
    
    # 时间
    (r"(\d{2}):(\d{2}):(\d{2})", r"\1点\2分\3秒"),
    (r"(\d{2}):(\d{2})", r"\1点\2分"),
    
    # 百分比
    (r"(\d+)\.(\d+)%", r"百分之\1点\2"),
    (r"(\d+)%", r"百分之\1"),
    
    # 股票代码（6位数字）
    (r"(?<![\d])\d{6}(?![\d])", lambda m: format_stock_code(m.group())),
]

def format_for_tts(text: str) -> str:
    """将数字格式化为口语化表达"""
    for pattern, replacement in NUMBER_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

def format_stock_code(code: str) -> str:
    """格式化股票代码"""
    return f"代码{code}"
```

### 4. 报告结构识别

```python
REPORT_PATTERNS = {
    "title": r"^涨停复盘报告$",
    "date": r"^(\d{4})年(\d{2})月(\d{2})日$",
    "section": r"^(市场概况|个股分析|资金观察|情绪分析|总结)$",
    "stock_entry": r"^第[一二三四五六七八九十\d]+只[：:]",
    "stock_code": r"股票代码[：:]\s*(\d{6})",
    "stock_name": r"股票名称[：:]\s*([^，。]+)",
    "limit_up_time": r"(\d{2})点(\d{2})分涨停",
    "drive_type": r"(政策驱动型|业绩驱动型|资金博弈型|概念驱动型)",
}

def identify_structure(text: str) -> Dict:
    """识别报告结构，返回元数据"""
    structure = {
        "type": "unknown",
        "level": 0,
        "metadata": {}
    }
    
    for pattern_name, pattern in REPORT_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            structure["type"] = pattern_name
            structure["metadata"][pattern_name] = match.groups()
            break
    
    return structure
```

### 5. 预加载机制

```javascript
// 前端预加载器
class TTSPrefetcher {
    constructor(options = {}) {
        this.cache = new Map();
        this.prefetchCount = options.prefetchCount || 3;
        this.maxCacheSize = options.maxCacheSize || 10;
    }
    
    async playSegment(index, segments) {
        // 播放当前
        await this.play(index);
        
        // 预加载后续
        for (let i = 1; i <= this.prefetchCount; i++) {
            if (index + i < segments.length) {
                this.prefetch(index + i, segments[index + i]);
            }
        }
        
        // 清理旧缓存
        this.cleanupCache(index);
    }
    
    async prefetch(index, segment) {
        if (this.cache.has(index)) return;
        
        // 后台生成音频
        const audioInfo = await this.generateAudio(segment);
        this.cache.set(index, audioInfo);
    }
    
    cleanupCache(currentIndex) {
        // 删除当前播放之前的内容
        for (const [key, value] of this.cache) {
            if (key < currentIndex - 1) {
                this.cache.delete(key);
            }
        }
    }
}
```

## 用户配置

```python
TTS_CONFIG = {
    # 分段策略
    "segment_strategy": "smart",  # original | line | smart
    
    # 停顿时长（秒）
    "pause_comma": 0.3,
    "pause_period": 0.8,
    "pause_paragraph": 2.0,
    
    # 分段阈值
    "short_sentence_threshold": 15,  # 小于此值合并
    "long_sentence_threshold": 60,   # 大于此值分割
    
    # 预加载
    "prefetch_count": 3,
    
    # 数字格式化
    "format_numbers": True,
    "format_dates": True,
    "format_stock_codes": True,
}
```

## 实施方案

### Phase 1: 基础优化（当前实施）
- [x] 智能分段算法
- [x] 停顿控制
- [x] 数字格式化
- [x] 用户配置切换

### Phase 2: 体验优化（后续）
- [ ] 报告结构识别
- [ ] 预加载机制
- [ ] 朗读模板

### Phase 3: 智能升级（后续）
- [ ] NLP语义分析
- [ ] 个性化语速
- [ ] 多音字纠正

## API设计

### 获取内容（带分段策略）
```
GET /api/reports/{type}/{filename}/content?strategy=smart

Response:
{
    "success": true,
    "data": {
        "segments": [
            {
                "id": 0,
                "text": "涨停复盘报告，2026年4月3日",
                "pause_after": 1.0,
                "type": "title",
                "audio_url": "/api/reports/tts/audio?hash=xxx"
            }
        ],
        "strategy": "smart",
        "total_segments": 38
    }
}
```

### 更新用户配置
```
POST /api/reports/tts/config

Body:
{
    "segment_strategy": "smart",
    "pause_period": 1.0,
    "prefetch_count": 3
}
```

## 文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `pdf_reader.py` | 修改 | 添加智能分段算法 |
| `tts_service.py` | 修改 | 添加数字格式化、停顿控制 |
| `report.py` | 修改 | 添加策略参数、配置API |
| `report-page.js` | 修改 | 添加策略切换UI、预加载 |
| `report.css` | 修改 | 添加配置面板样式 |
| `reports.html` | 修改 | 添加策略选择器 |

## 兼容性

- 向后兼容：保留 `original` 策略
- 默认策略：`smart`（新用户）
- 用户可切换：随时在三种策略间切换

## 测试用例

```python
# 测试智能分段
def test_smart_segment():
    text = "第一只：股票代码600001。该股票于10点30分涨停。"
    
    # original策略
    result_original = smart_segment(text, "original")
    assert len(result_original) == 2  # 两句分开
    
    # smart策略
    result_smart = smart_segment(text, "smart")
    assert len(result_smart) == 1  # 合并为一句
    assert "代码600001" in result_smart[0]  # 数字已格式化

# 测试数字格式化
def test_format_numbers():
    text = "2026-04-07 10:30 上涨5.5%"
    result = format_for_tts(text)
    assert result == "2026年4月7日 10点30分 上涨百分之5点5"
```

---

## 附录：参考产品

1. **微信读书**：智能分段、流畅阅读
2. **科大讯飞语音阅读**：段落智能合并、数字朗读优化
3. **Apple Books**：章节识别、阅读模式切换
4. **Voice Dream**：语义分析、多音字处理

---

*文档版本：v1.0*
*最后更新：2026-04-07*
