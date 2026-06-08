# 智能日报功能设计文档 v2

## 一、功能概述

在报告中心增加"智能报告"功能，基于 AI 分析结果（4张detail表），自动生成重大利好日报。
支持折叠式阅读、左侧导航定位、文字搜索高亮。

## 二、数据源与筛选

| 数据源 | 表名 | 条数 | 筛选条件 | 时间字段 |
|--------|------|------|----------|----------|
| 领域分析 | analysis_domain_detail_2026 | 60条 | `news_type='利好' AND news_size='重大'` | event_time |
| 新闻分析 | analysis_news_detail_2026 | 30条 | `news_type='利好' AND composite_score>=50` | publish_time |
| 公告分析 | analysis_notice_detail_2026 | 10条 | `overnight_score>=70` | notice_date |
| 涨停分析 | analysis_ztb_detail_2026 | 全部 | `has_expect=1` | trade_date |

时间范围：`trading_day_util.get_start_end(date)` → [上一交易日, 下一交易日]

## 三、分级规则（纯排名制）

| 级别 | 图标 | 排名范围 | 展示方式 |
|------|------|----------|----------|
| 🔴 TOP级 | 🔴 | 第1-10名 | 卡片（折叠） |
| 🟠 重要级 | 🟠 | 第11-30名 | 卡片（折叠） |
| 🟡 关注级 | 🟡 | 第31名及以后 | 卡片（折叠） |

## 四、卡片展示结构（折叠式）

每条卡片分为**始终可见**和**折叠内容**两部分：

```
第1行（始终可见）：排名 + 综合分 + 标题 + 来源 + 时间
第2行（始终可见）：💡 核心逻辑
折叠区（点击展开）：领域/板块/概念/股票/深度评分
```

### 各数据源字段映射

| 数据源 | 标题 | 来源+时间 | 核心逻辑 | 折叠内容 |
|--------|------|-----------|----------|----------|
| 领域分析 | `key_event` | `event_source` + `event_time` | `reason_analysis` | 主/子领域+板块+概念+股票+深度分析 |
| 新闻分析 | `title` | `source` + `publish_time` | `sector_details`关联原因 | 板块+概念+龙头+深度分析 |
| 公告分析 | `notice_title` | `stock_name` + `notice_date` | `judgment_basis` | 关键要点+评分+影响+策略 |
| 涨停分析 | `stock_name(code)` | `trade_date` + `zt_time` | `influence_msg` | 板块+概念+龙头+涨停原因+预期+深度 |

## 五、报告页面结构

```
┌──────────┐ ┌──────────────────────────────────────┐
│ 🔍 搜索   │ │                                      │
│ [______] │ │  封面（标题+日期+阅读时间）             │
│ 3/15 ↑↓  │ │                                      │
│          │ │  📊 今日速览（4个统计卡片）             │
│ 📋 目录   │ │                                      │
│ • 今日速览│ │  🔥 头条摘要（TOP 10）                │
│ • 头条摘要│ │                                      │
│ • 第一章  │ │  🏭 第一章 · 领域重大利好（60条）      │
│ • 第二章  │ │                                      │
│ • 第三章  │ │  📰 第二章 · 重大新闻利好（30条）      │
│ • 第四章  │ │                                      │
│ • 板块热度│ │  📋 第三章 · 高价值公告（10条）        │
│ • 概念热度│ │                                      │
│          │ │  📈 第四章 · 涨停分析（全部）           │
│          │ │                                      │
│          │ │  📊 附录 · 板块热度 TOP20              │
│          │ │  💡 附录 · 概念热度 TOP20              │
└──────────┘ └──────────────────────────────────────┘
```

### 左侧导航功能
- 固定位置，不随页面滚动
- 点击跳转到对应章节（锚点）
- 滚动时自动高亮当前章节
- 搜索框在目录上方

### 文字搜索功能
- 输入关键词 → 高亮所有匹配（黄色背景）
- 显示匹配数量 "3/15"
- ↑↓ 按钮跳转匹配项
- 当前匹配项橙色高亮
- 支持中文

## 六、封面信息

```
🧠 GS2026 智能日报
2026年6月5日（周四）
时间窗口：2026-06-05 ~ 2026-06-08
📖 缩略阅读：约 50,823 字 · 预计 102 分钟
📚 全文阅读：约 150,228 字 · 预计 300 分钟
```

## 七、技术实现

### 7.1 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/smart_report_service.py` | 修改 | 核心服务（数据查询+HTML生成+导航+搜索） |
| `routes/report.py` | 已完成 | `/api/reports/smart/generate` |
| `services/report_service.py` | 已完成 | SUPPORTED_EXTENSIONS含.html |
| `services/document_reader.py` | 已完成 | HTMLReader支持TTS |
| `static/js/pages/report-page.js` | 已完成 | 智能报告生成按钮 |
| `docs/smart_report_design.md` | 本文件 | 设计文档 |

### 7.2 HTML内嵌架构

```html
<!DOCTYPE html>
<html>
<head>
  <style>/* 导航+搜索+卡片样式 */</style>
</head>
<body>
  <nav id="report-nav">
    <!-- 搜索框 -->
    <!-- 目录链接 -->
  </nav>
  <main id="report-content">
    <!-- 封面 -->
    <!-- 各章节（带id锚点） -->
  </main>
  <script>/* 搜索+滚动监听JS */</script>
</body>
</html>
```

### 7.3 API接口

```
POST /api/reports/smart/generate
Body: { "date": "2026-06-05" }  // 可选，默认当天
Response: { "success": true, "path": "...", "stats": {...} }
```

## 八、安全保证（不影响现有功能）

1. `smart_report_service.py` → 独立服务，不修改其他service
2. `routes/report.py` → 仅追加新路由
3. 导航/搜索 → 纯HTML内嵌（CSS+JS），不影响外部页面
4. 生成的HTML → 独立文件在iframe中展示
5. `trading_day_util` → 只读调用
6. TTS阅读 → HTMLReader提取纯文本，导航/搜索JS不影响
