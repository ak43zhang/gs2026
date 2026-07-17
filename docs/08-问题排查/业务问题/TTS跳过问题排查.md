# TTS阅读跳过问题排查指南

## 问题现象
- 读完第1段后直接跳到第3段
- 跳过第2段（"第一部分：市场概况..."）

## 排查步骤

### 步骤1: 验证MD5实现

在浏览器中打开：
```
http://localhost:8080/static/test_md5_verify.html
```

**期望结果：** 所有测试显示 PASS

**如果 FAIL：** MD5实现有问题，需要修复

### 步骤2: 清除浏览器缓存

1. 按 `Ctrl+Shift+R` 强制刷新（或 `Cmd+Shift+R` on Mac）
2. 或者按 `F12` → Network → 勾选 "Disable cache" → 刷新

### 步骤3: 检查控制台日志

1. 按 `F12` 打开开发者工具
2. 切换到 Console 标签
3. 打开报告，点击"阅读"
4. 观察日志输出：

**正常情况：**
```
Version changed, clearing caches...
Loading content with strategy: original
Preparing TTS with strategy: original
First 3 segment hashes:
  [0] bae526b5955ac1f1... -> matched
  [1] bd79330f5c920d77... -> matched
  [2] 8ea9d399b2c1ef59... -> matched
TTS prepared: 943/943 segments matched by hash
```

**如果看到：**
```
WARNING: Low hash match rate (xxx/943), falling back to index matching
Fallback index matching applied
```

这说明哈希匹配失败，但已自动回退到索引匹配。

### 步骤4: 手动测试

在浏览器控制台运行：

```javascript
// 测试MD5
ReportReader._md5("test")
// 应该输出: 098f6bcd4621d373cade4e832627b4f6

// 检查第二段
ReportReader.segments[1]
// 应该显示该段落的详细信息

// 检查第二段是否有音频URL
ReportReader.segments[1].audio_url
// 应该输出音频URL，不是 undefined
```

### 步骤5: 强制重置

如果以上都正常但问题仍存在：

```javascript
// 在控制台运行
localStorage.clear();
location.reload();
```

## 后端验证

运行测试脚本：
```bash
cd ~/.stepclaw/workspace
python test_final_verify.py
```

**期望输出：**
```
[PASS] 所有段落都有音频，不会跳过！
[OK] 播放顺序完全连续，没有跳过！
```

## 常见原因

### 1. 浏览器缓存
- 浏览器加载了旧的 report-page.js
- **解决：** 强制刷新或禁用缓存

### 2. localStorage 缓存
- 保存了旧的策略设置
- **解决：** 版本号机制会自动清除

### 3. MD5 实现不一致
- 前端MD5与后端Python MD5结果不同
- **解决：** 已添加fallback到索引匹配

### 4. 策略不一致
- loadContent 和 prepareTTS 使用不同策略
- **解决：** 已统一默认值为 'original'

## 最新修复

### commit 5685a19
- 添加版本号机制，强制清除缓存
- 当哈希匹配率低于50%时，自动回退到索引匹配
- 确保即使MD5有问题也能正常播放

### 测试页面
- `/static/test_md5_verify.html` - 验证MD5实现
- `/static/js/pages/report-debug.js` - 调试工具

## 如果仍有问题

1. 在浏览器控制台运行：
   ```javascript
   ReportReader.resetStrategy();
   location.reload();
   ```

2. 检查网络请求：
   - 按 `F12` → Network
   - 查看 `/tts/prepare` 请求的响应
   - 确认返回的 segments 数量

3. 联系开发：
   - 提供浏览器控制台截图
   - 提供 `/static/test_md5_verify.html` 的结果
