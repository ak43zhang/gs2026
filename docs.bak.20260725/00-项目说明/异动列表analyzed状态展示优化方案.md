# 异动列表 analyzed 状态展示优化方案

## 当前行为

```
ai_status = 'analyzed' 时：
  显示：✅ 基础分析完成，等待主线归类...
  （只有一行提示，不展示分析内容）
```

## 期望行为

```
ai_status = 'analyzed' 时：
  ┌─────────────────────────────────────┐
  │ ⏳ 基础分析完成，等待主线归类...     │  ← 醒目状态提示（蓝色背景）
  ├─────────────────────────────────────┤
  │ 🤖 AI基础分析                       │
  │ 异动原因：xxx                       │
  │ 置信度：xxx                         │
  │ 涉及板块：xxx                       │
  │ 涉及概念：xxx                       │
  │ 共振标的：xxx                       │
  │ 预判吻合：xxx                       │
  │ 风险等级：xxx                       │
  │ 次日预判：xxx                       │
  │ 操作建议：xxx                       │
  └─────────────────────────────────────┘
```

## 修改方案

将第2049-2050行：
```javascript
} else if (item.ai_status === 'analyzed') {
    html += '<div class="ai-pending" style="color:#667eea;">✅ 基础分析完成，等待主线归类...</div>';
```

改为：
```javascript
} else if (item.ai_status === 'analyzed' && item.ai_analysis) {
    var ai = item.ai_analysis;
    html += '<div class="ai-section">';
    // 醒目状态提示
    html += '<div style="background:#e6f4ff;border:1px solid #91caff;border-radius:4px;padding:6px 10px;margin-bottom:8px;color:#1677ff;font-size:13px;">⏳ 基础分析完成，等待主线归类...</div>';
    // 展示基础分析内容（与done状态相同，但不含主线归属）
    html += '<div class="ai-label">🤖 AI基础分析</div>';
    if (ai['异动原因']) html += '<div class="ai-row"><span class="key">异动原因：</span>' + ai['异动原因'] + '</div>';
    if (ai['原因置信度']) html += '<div class="ai-row"><span class="key">置信度：</span>' + ai['原因置信度'] + '</div>';
    var sectors = ai['涉及板块'] || ai['联动板块'];
    if (sectors && sectors.length) html += '<div class="ai-row"><span class="key">涉及板块：</span>' + sectors.join('、') + '</div>';
    var concepts = ai['涉及概念'] || ai['联动概念'];
    if (concepts && concepts.length) html += '<div class="ai-row"><span class="key">涉及概念：</span>' + concepts.join('、') + '</div>';
    if (ai['共振标的'] && ai['共振标的'].length) {
        html += '<div class="ai-row" style="margin-top:8px;"><span class="key">🔗 共振标的：</span></div>';
        html += '<div class="ai-detail-list">';
        ai['共振标的'].forEach(function(s) {
            html += '<div class="ai-detail-item">' + (s.code || '') + ' <b>' + (s.name || '') + '</b> - <span style="color:#667eea;">' + (s.reason || '') + '</span></div>';
        });
        html += '</div>';
    }
    var matchClass = ai['预判吻合度'] || 'none';
    var matchLabel = {'exact': '✅ 完全吻合', 'partial': '⚠️ 部分吻合', 'none': '❌ 未预判'}[matchClass] || matchClass;
    html += '<div class="ai-row"><span class="key">预判吻合：</span><span class="match-badge ' + matchClass + '">' + matchLabel + '</span></div>';
    if (ai['风险等级']) html += '<div class="ai-row"><span class="key">风险等级：</span>' + ai['风险等级'] + '</div>';
    if (ai['次日预判']) html += '<div class="ai-row"><span class="key">次日预判：</span>' + ai['次日预判'] + '</div>';
    if (ai['操作建议']) html += '<div class="ai-row"><span class="key">操作建议：</span>' + ai['操作建议'] + '</div>';
    html += '</div>';
} else if (item.ai_status === 'analyzed') {
    // ai_analysis 为空时的兜底
    html += '<div class="ai-pending" style="color:#667eea;">✅ 基础分析完成，等待主线归类...</div>';
```

## 视觉效果

### analyzed 状态（修改后）

```
┌──────────────────────────────────────┐
│ ⏳ 基础分析完成，等待主线归类...      │  蓝色背景提示条
├──────────────────────────────────────┤
│ 🤖 AI基础分析                        │
│ 异动原因：资金集中涌入，量价齐升      │
│ 置信度：high                         │
│ 涉及板块：光伏、新能源                │
│ 涉及概念：碳中和、储能                │
│ 🔗 共振标的：                        │
│    688596 正帆科技 - 同板块联动        │
│ 预判吻合：✅ 完全吻合                 │
│ 风险等级：低                          │
│ 次日预判：看涨                        │
│ 操作建议：可关注                      │
└──────────────────────────────────────┘
```

### done 状态（不变）

唯一区别：没有蓝色提示条，多了"📊 主线归属"部分。

## 审核要点

1. 保持与 done 状态一致的渲染逻辑，仅区别：
   - 有蓝色提示条
   - 标题为"AI基础分析"而非"AI分析结果"
   - 不显示"主线归属"（因为还没做）
2. ai_analysis 为空时兜底显示原来的提示
3. 样式与现有一致，不引入新 CSS

审核通过后实施。
