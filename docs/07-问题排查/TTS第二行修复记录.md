# TTS第二行阅读问题修复

## 问题描述
ZTB_Report_20260403_TTS.pdf 阅读时，第一行读完后直接跳到第三行，跳过第二行。

第二行内容：
```
第一部分：市场概况
今日市场概况如下：
沪深两市共计38只个股涨停
```

## 排查结果

### 后端测试
```
Segment 2 (index 1):
  Text: 第一部分：市场概况\n今日市场概况如下：\n沪深两市共计38只个股涨停
  MD5: bd79330f5c920d77223ef20fdc836322
  Matched: ✓
  Audio URL: /api/reports/tts/audio?text=bd79330f5c920d77223ef20fdc836322&voice=xiaoxiao
  Duration: 8.5s
  Ready: True

Overall Match Rate: 943/943 (100%)
```

**结论：后端完全正常，所有段落都匹配成功。**

### 问题定位
问题出在前端MD5实现：
1. 原MD5实现使用了 `unescape(encodeURIComponent(string))` 处理UTF-8
2. 这在某些浏览器中可能产生不一致的结果
3. 导致前端计算的哈希与后端不匹配

## 修复方案

### 1. 替换MD5实现 (commit f2c7470)
使用更可靠的简化版MD5算法，避免浏览器兼容性问题。

### 2. 添加调试工具
创建 `report-debug.js`，可在浏览器控制台运行：
```javascript
// 测试MD5
TTSDebug.testMD5()

// 检查段落
TTSDebug.checkSegment(1)  // 检查第二行

// 检查所有段落
TTSDebug.checkSegments()
```

### 3. 添加调试日志
在 `prepareTTS` 中添加详细日志，可在浏览器控制台查看。

## 验证步骤

### 步骤1: 清除浏览器缓存
1. 按 F12 打开开发者工具
2. 切换到 Network 标签
3. 勾选 "Disable cache"
4. 刷新页面

### 步骤2: 验证MD5
在浏览器控制台运行：
```javascript
// 应该输出: bd79330f5c920d77223ef20fdc836322
ReportReader._md5("第一部分：市场概况\n今日市场概况如下：\n沪深两市共计38只个股涨停")
```

### 步骤3: 测试阅读
1. 打开报告中心
2. 选择 ZTB_Report_20260403_TTS.pdf
3. 点击"阅读"
4. 打开浏览器控制台 (F12)
5. 观察日志输出

期望看到：
```
Loading content with strategy: original
Preparing TTS with strategy: original
First 3 segment hashes:
  [0] bae526b5955ac1f1... -> matched
  [1] bd79330f5c920d77... -> matched
  [2] 8ea9d399b2c1ef59... -> matched
TTS prepared: 943/943 segments matched
```

## 如果仍有问题

### 检查1: 策略一致性
确保 `loadContent` 和 `prepareTTS` 使用相同策略：
```javascript
// 在控制台运行
ReportReader.segmentStrategy
// 应该输出: "original"
```

### 检查2: 手动重置
```javascript
// 在控制台运行
ReportReader.resetStrategy()
location.reload()
```

### 检查3: 查看第二行详情
```javascript
TTSDebug.checkSegment(1)
```

## 文件变更

| 文件 | 变更 |
|------|------|
| `report-page.js` | 替换MD5实现，添加调试日志 |
| `report-debug.js` | 新增调试工具（可选加载） |

## Git提交

- `f2c7470` fix: 修复前端MD5实现，使用更可靠的算法
