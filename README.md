# GS2026 Dashboard2 项目文档

## 项目概述

GS2026 Dashboard2 是一个数据采集和监控面板，支持股票、债券、行业数据的采集和AI分析。

**当前版本**: v2026.4.15  
**主要更新**: 分析中心四大模块完整功能上线

## 功能模块

### 1. 数据监控
- 股票监控
- 债券监控
- 行业监控
- 大盘信号监控
- 股债联动监控

### 2. 数据采集
- **基础采集** (16个任务)
  - 涨停板数据、涨停炸板数据、指数宽基
  - 今日龙虎榜、融资融券、公司动态
  - 历史龙虎榜、通达信风险
  - 同花顺行业、同花顺行业成分
  - Baostock数据、问财基础数据、问财热股数据
  - 可转债base、可转债daily、板块概念
  
- **消息采集** (10个任务)
  - 财经早餐、全球快讯、财联社历史等
  
- **风险采集** (4个任务)
  - 问财风险-日、问财风险-年、公告风险、Akshare风险

### 3. 分析中心 (v2026.4.15 重大更新)
四大独立分析模块，支持DeepSeek AI深度分析：

#### 📈 涨停分析 (`/ztb-analysis`)
- 涨停股票列表展示
- **市场板块筛选**：沪深主板、科创板、创业板、ST板块、龙虎榜、无龙虎榜
- 涨停时段分布（竞价/早盘/午盘/尾盘竞价）
- 个股详情面板（涨停原因、预期消息、延续性分析）

#### 📰 新闻分析 (`/news-analysis`)
- 新闻列表展示与筛选
- **当日统计**：总新闻、利好、利空、重大
- **热点板块排行**：重大利好消息板块统计
- 消息大小标记（重大/大/中/小）
- 详情面板（AI评分、板块/概念/个股关联）

#### 📋 公告分析 (`/notice-analysis`)
- 公告列表展示与筛选
- **当日统计**：总公告、利好、利空、中性
- 风险等级标记（高/中/低）
- 公告详情查看

#### 🌐 领域分析 (`/domain-analysis`)
- 领域事件列表展示
- **当日统计**：总事件、利好、利空、重大
- **热点板块排行**：重大利好事件板块统计
- 消息大小标记
- 详情面板（事件描述、原因分析、深度分析、AI评分）

### 4. 数据分析 (后台)
- **DeepSeek AI分析** (5个任务)
  - 领域事件分析
  - 财联社数据分析
  - 综合数据分析
  - 涨停板数据分析
  - 公告分析

## 技术栈

- **后端**: Python Flask + Redis + SQLAlchemy
- **前端**: JavaScript (ES6+) + CSS Grid/Flexbox
- **数据库**: MySQL 8.0
- **进程管理**: 自定义ProcessManager + Redis分布式锁
- **AI分析**: DeepSeek API

## 项目结构

```
gs2026/
├── src/gs2026/dashboard2/          # Dashboard2主项目
│   ├── app.py                      # Flask应用入口
│   ├── routes/                     # API路由
│   │   ├── collection.py           # 数据采集API
│   │   ├── analysis.py             # 数据分析API
│   │   ├── analysis_center.py      # 涨停分析路由
│   │   ├── news.py                 # 新闻分析路由
│   │   ├── notice_analysis.py      # 公告分析路由
│   │   ├── domain_analysis.py      # 领域分析路由
│   │   └── ...
│   ├── services/                   # 服务层
│   │   ├── news_service.py
│   │   ├── notice_analysis_service.py
│   │   ├── domain_analysis_service.py
│   │   └── ztb_analysis_service.py
│   ├── static/                     # 静态资源
│   │   ├── css/
│   │   └── js/
│   └── templates/                  # HTML模板
│       ├── analysis_center.html    # 涨停分析页面
│       ├── news.html               # 新闻分析页面
│       ├── notice_analysis.html    # 公告分析页面
│       └── domain_analysis.html    # 领域分析页面
├── src/gs2026/dashboard/           # 原版Dashboard
├── src/gs2026/analysis/            # AI分析脚本
│   └── worker/message/deepseek/    # DeepSeek分析处理器
├── docs/                           # 项目文档
└── sql/                            # SQL脚本
```

## 快速启动

### 启动 Dashboard2
```bash
cd F:\pyworkspace2026\gs2026
python start_dashboard2_flask.py
```

访问: http://localhost:8080

### 四大分析模块入口
- 涨停分析: http://localhost:8080/ztb-analysis
- 新闻分析: http://localhost:8080/news-analysis
- 公告分析: http://localhost:8080/notice-analysis
- 领域分析: http://localhost:8080/domain-analysis

## 主要功能特性

### 1. 消息大小/类型智能计算
- 不再依赖AI返回的分类，改为根据评分客观计算
- **消息大小**: 综合评分 ≥90=重大, ≥60=大, ≥30=中, <30=小
- **消息类型**: 业务影响分 >0=利好, <0=利空, =0=中性

### 2. 热点板块统计
- 只统计**重大利好消息**的板块分布
- 按消息数量和平均评分排序
- 支持点击筛选

### 3. 市场板块筛选（涨停分析）
支持7种筛选条件：
- 沪深主板（600/601/603/605/000/001/002/003开头）
- 科创板（688开头）
- 创业板（300/301开头）
- ST板块（名称以ST或*ST开头）
- 龙虎榜（有龙虎榜分析数据）
- 无龙虎榜（无龙虎榜分析数据）

### 4. 当日统计面板
- 跟随日期选择器自动更新
- 实时统计总数量、利好、利空、重大/中性

## 配置说明

### 分析模块配置
配置文件: `src/gs2026/dashboard2/routes/analysis_modules.py`

### 数据库表
分析中心使用以下数据表：
- `analysis_news_detail_2026` - 新闻分析数据
- `analysis_notice_detail_2026` - 公告分析数据
- `analysis_domain_detail_2026` - 领域分析数据
- `analysis_ztb_detail_2026` - 涨停分析数据

## 更新日志

### v2026.4.15 - 分析中心完整功能上线
- ✅ 涨停分析：市场板块筛选功能
- ✅ 新闻分析：当日统计、热点板块、详情面板
- ✅ 公告分析：当日统计、风险等级筛选
- ✅ 领域分析：当日统计、热点板块、详情面板、分页加载
- ✅ 消息大小/类型计算逻辑修复
- ✅ 热点板块只统计重大利好消息
- ✅ 导航栏样式统一
- ✅ 路由重命名统一（/ztb-analysis, /news-analysis, /notice-analysis, /domain-analysis）

### v2026.3.27 - Dashboard2基础功能
- ✅ 数据采集面板模块化架构
- ✅ 进程管理优化
- ✅ Redis连接池优化

## 开发团队

- **项目**: GS2026 Dashboard2
- **版本**: v2026.4.15
- **分支**: feature/websocket-notification → main (已合并)

## 文档索引

| 文档 | 说明 |
|------|------|
| `docs/dashboard2_analysis_design.md` | 数据分析模块详细设计 |
| `docs/stock_bond_industry_mapping.sql` | 股债行业映射SQL |
| `docs/2026-03-27.md` | 开发日志 |

## 贡献者

- 主要开发: AI Assistant

## 许可证

私有项目
