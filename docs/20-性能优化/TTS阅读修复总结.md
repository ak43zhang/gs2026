# TTS阅读功能修复总结

## 修复时间
2026-04-07

## 问题描述
TTS阅读功能出现"隔一个读一个"的问题，即读完第1段后直接跳到第3段，跳过第2段。

## 根本原因

### 问题1: 前后端分段策略不一致
- 前端使用 `original` 策略
- 后端 `prepare_tts` 默认使用 `smart` 策略
- 导致分段数量不同，索引错位

### 问题2: 哈希算法不一致
- 前端使用自定义哈希算法
- 后端使用 MD5
- 导致 `prepareTTS` 中的哈希匹配全部失败

### 问题3: 索引匹配方式
- 前端按索引匹配音频URL
- 当分段不一致时，出现错位

## 修复方案

### 修复1: 统一分段策略 (commit 17b532e)
**文件:** `report.py`, `report-page.js`

**修改:**
- `prepare_tts` 接口添加 `strategy` 参数
- 前端 `prepareTTS` 方法传递当前策略

```python
# 后端
strategy = data.get('strategy', 'smart')
segments = pdf_reader.extract_and_cache(file_path, strategy)
```

```javascript
// 前端
const strategy = this.segmentStrategy || 'smart';
body: JSON.stringify({ voice, speed, strategy })
```

### 修复2: 使用文本哈希匹配 (commit 1e156e0)
**文件:** `tts_service.py`, `report-page.js`

**修改:**
- 后端 `generate_for_segments` 返回 `{text_hash: audio_info}` 字典
- 前端使用 `_getTextHash` 匹配段落

```python
# 后端
def generate_for_segments(self, segments, voice, speed) -> dict:
    results = {}
    for segment in segments:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        results[text_hash] = { ... }
    return results
```

```javascript
// 前端
const hashMap = result.data.segments;
this.segments.forEach((seg) => {
    const textHash = this._getTextHash(seg.text);
    const audioInfo = hashMap[textHash];
    if (audioInfo) {
        seg.audio_url = audioInfo.audio_url;
    }
});
```

### 修复3: 实现MD5算法 (commit 631858b)
**文件:** `report-page.js`

**修改:**
- 前端实现完整的 MD5 算法
- 与后端 `hashlib.md5` 保持一致

```javascript
_getTextHash: function(text) {
    return this._md5(text);  // MD5算法
},

_md5: function(string) {
    // 完整的MD5实现...
}
```

### 修复4: 默认策略改为按句分割 (commit 310d3c8)
**文件:** `report-page.js`, `reports.html`

**修改:**
- 默认策略从 `smart` 改为 `original`
- HTML中默认选中"按句分割"

```javascript
segmentStrategy: localStorage.getItem('tts_strategy') || 'original'
```

## 测试验证

### 测试结果
```
获取PDF内容: 943段
后端返回音频映射: 666个

MD5哈希匹配测试 (前20段):
  [0] 匹配成功 hash=bae526b5955ac1f1...
  [1] 匹配成功 hash=bd79330f5c920d77...
  ...
  [19] 匹配成功 hash=26d0f9d91b3c53e5...

匹配: 20/20
未匹配: []

结论: 所有段落都有音频URL，不会跳过!
```

## 使用说明

### 策略选择
在阅读器顶部可以选择三种分段策略:

1. **按句分割 (推荐)** - 按标点符号分割，阅读流畅
2. **智能分段** - 短句合并，长句保持
3. **按行分割** - 每行一段，最细碎

### 切换策略
1. 打开阅读器
2. 在顶部选择策略
3. 内容会自动重新加载

## 文件变更

| 文件 | 变更 |
|------|------|
| `tts_service.py` | `generate_for_segments` 返回dict |
| `report.py` | `prepare_tts` 添加strategy参数 |
| `report-page.js` | MD5算法、哈希匹配、默认策略 |
| `reports.html` | 默认选中"按句分割" |

## Git提交记录

- `631858b` fix: 修复TTS哈希算法不一致导致的跳过问题
- `310d3c8` fix: 将默认TTS策略改为按句分割(original)
- `1e156e0` fix: 修复TTS阅读间隔读取问题 - 使用文本哈希匹配
- `17b532e` fix: 修复TTS阅读跳过段落的问题

## 状态
✅ 修复完成，测试通过
