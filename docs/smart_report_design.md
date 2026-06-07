# 智能日报功能设计文档

## 一、功能概述

在报告中心增加"智能报告"功能，基于 AI 分析结果（4张detail表），自动生成约30分钟阅读量的重大利好日报。

## 二、数据源与筛选

| 数据源 | 表名 | 条数 | 筛选条件 | 时间字段 |
|--------|------|------|----------|----------|
| 领域分析 | analysis_domain_detail_2026 | 60条 | `news_type='利好' AND news_size='重大'` | event_time |
| 新闻分析 | analysis_news_detail_2026 | 30条 | `news_type='利好' AND composite_score>=50` | publish_time |
| 公告分析 | analysis_notice_detail_2026 | 10条 | `overnight_score>=70` | notice_date |
| 涨停分析 | analysis_ztb_detail_2026 | 全部 | `has_expect=1` | trade_date |

时间范围：`trading_day_util.get_start_end(date)` → [上一交易日, 下一交易日]

## 三、分级规则（纯排名制）

所有数据源统一按评分排序后，按排名分级：

| 级别 | 图标 | 排名范围 | 展示方式 |
|------|------|----------|----------|
| 🔴 TOP级 | 🔴 | 第1-10名 | 详细卡片（全字段展开） |
| 🟠 重要级 | 🟠 | 第11-30名 | 中等卡片（核心字段） |
| 🟡 关注级 | 🟡 | 第31名及以后 | 简洁表格行 |

排序字段：
- 领域分析：composite_score DESC
- 新闻分析：composite_score DESC
- 公告分析：overnight_score DESC
- 涨停分析：continuity DESC, zt_time_range ASC (early>midday>late)

## 四、报告结构

### 4.1 封面区

```
🧠 GS2026 智能日报
2026年6月5日（周四）
时间窗口：2026-06-05 ~ 2026-06-08
```

### 4.2 今日速览

统计卡片：
- 领域利好 60 | 新闻利好 30 | 高分公告 10 | 涨停有预期 XX

### 4.3 🔥 头条摘要（TOP 10）

从全部4个数据源中，取综合评分最高的10条，每条一句话概括：
```
1. [领域-军事安全] 中国宣布在台海周边设立禁飞区，军工全线受益
2. [新闻] FDA批准XX药物上市，创新药板块迎重大催化
3. [公告-岱勒新材] 一季报净利润同比+250%，超市场预期
4. [涨停-东方通信] 连板强势，6G概念龙头确认
...（共10条）
```

### 4.4 第一章 · 领域重大利好（60条）

#### 🔴 TOP级（第1-10名）详细卡片

```
① [主领域/子领域] 综合分:XXX

   📰 事件：XXXXXXXXX
   📍 来源：XXX | 时间：YYYY-MM-DD HH:MM

   📌 关联板块：XXX | XXX | XXX
   📌 关联概念：XXX | XXX | XXX
   📌 关联股票：600760 | 000768 | 600893

   💡 核心逻辑：
   XXXXXXXXXXXXXXXXXXXXXX

   📊 深度评分与分析：
   • 政策支持(5)：XXXXX具体原因描述
   • 技术突破(5)：XXXXX具体原因描述
   • 资金改善(4)：XXXXX具体原因描述
   • 运营效率(3)：XXXXX具体原因描述
   • 成本控制(3)：XXXXX具体原因描述
```

#### 🟠 重要级（第11-30名）中等卡片

```
⑪ [主领域/子领域] 综合分:XXX
   事件：XXXXXXXXX | 来源：XXX
   板块：XXX | 概念：XXX | 股票：XXX
   核心逻辑：XXXXXXXXX
```

#### 🟡 关注级（第31-60名）简洁表格

```
# | 领域 | 事件（截断50字） | 综合分 | 板块 | 股票
31 | 新能源/光伏 | 国务院发布... | 75 | 光伏设备 | 600XXX
32 | ...
```

### 4.5 第二章 · 重大新闻利好（30条）

格式同领域分析，分三级展示。

TOP级额外展示：
- 板块明细（sector_details中的关联原因）
- 深度分析（deep_analysis）

### 4.6 第三章 · 高价值公告（10条）

全部详细展示（仅10条，不分级）：
```
① [股票代码 股票名称] 隔夜分:XXX
   📋 公告标题：XXXXXXXXX
   📅 公告日期：YYYY-MM-DD
   🏷️ 类型：XXX | 风险等级：X
   
   📌 关键要点：
   • XXXXXX
   • XXXXXX
   
   📊 评分：隔夜策略分XX | 风险分XX | 类型分XX
   
   💡 短期影响：XXXXXXXXX
   💡 中期影响：XXXXXXXXX
   🎯 隔夜策略：XXXXXXXXX
```

### 4.7 第四章 · 涨停有预期（全部）

按封板时段分组展示：

#### ⚡ 早盘涨停（early）
```
① 股票名称(代码) | 封板时间 | 连板数X
   板块：XXX | 概念：XXX
   龙头股：XXX
   涨停原因：XXXXXXXXX
   预期消息：XXXXXXXXX
   深度分析：XXXXXXXXX
```

#### 🕐 午盘涨停（midday）
（格式同上）

#### 🌙 尾盘涨停（late）
（格式同上）

### 4.8 附录 · 板块热力图

跨4张表统计板块出现频次，取TOP 20：
```
军工(12次) | 新能源(9次) | 半导体(7次) | AI(6次) | ...
```

## 五、技术实现

### 5.1 新增文件（不影响现有功能）

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/smart_report_service.py` | 新建 | 数据查询+HTML生成 |
| `routes/report.py` | 追加路由 | `/api/reports/smart/generate` |
| `static/css/smart-report.css` | 新建 | 报告内嵌样式 |
| `static/js/pages/report-page.js` | 微改 | "智能报告"类型下显示生成按钮 |
| `G:/report/智能报告/` | 自动创建 | 报告存储目录 |

### 5.2 API接口

```
POST /api/reports/smart/generate
Body: { "date": "2026-06-05" }  // 可选，默认当天
Response: { "success": true, "path": "智能报告/智能日报_2026-06-05.html" }
```

### 5.3 安全保证（不影响现有功能）

1. `smart_report_service.py` → 全新文件，零修改现有service
2. `routes/report.py` → 仅在文件末尾追加新路由
3. CSS → 独立文件，HTML内嵌引用
4. JS → 条件追加（仅"智能报告"类型下激活）
5. 生成的HTML → 独立文件，iframe展示
6. `trading_day_util` → 只读调用
