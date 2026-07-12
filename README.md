# GS2026 量化投研平台

## 项目概述

GS2026 是一个面向量化投资的综合性投研平台，集数据采集、实时监控、AI分析、量化回测于一体。

**当前版本**: v2026.7.13  
**核心定位**: 盘中异动监控 + 量化策略回测 + 市场主线分析

---

## 核心功能模块

### 1. 实时监控 (`/monitor`)

#### 股票上攻排行
- 实时股票涨幅排行监控
- 多维度过滤：仅前N行业、仅前N金额、隐藏绿名单
- 面板化过滤器，支持扩展
- 历史日期回溯 + 时间点查询

#### 债券上攻排行
- 可转债实时涨幅监控
- 斜率指标体系：加权斜率、变化率、加速度
- 大盘/个券共振检测
- 金额排名 + 流动性指标
- 列配置系统（动态渲染 + 列设置UI + 排序）

#### 行业板块排行
- 行业涨跌幅实时监控
- 历史日期回溯支持
- 折叠功能（空间优化）

#### 大盘信号监控
- 加权斜率指标 `mkt_weighted_slope_2m`
- 变化率 `mkt_change_1m_pct`
- 价格加速度 `mkt_price_acceleration`
- 大盘趋势指标（mkt_slope_short/long + mkt_peak_vol_bias + mkt_high_distance）

#### 股债联动监控
- 股票-债券关联分析
- 实时联动信号

### 2. 盘中异动 (`/anomaly`)

#### 市场主线综合分析系统
- **里程碑触发AI合成**：formation(2只) / confirmed(5只)
- **主线动态追踪**：发酵期 → 扩散期 → 高潮期 → 分歧期
- **发展时间线**：龙头→跟风→补涨完整链条
- **展示维度**：驱动逻辑 / 催化事件 / 持续性判断 / 阶段标签

#### 异动股票AI分析
- 涨停原因识别
- 主线归属判定
- 延续性分析
- 股票代码/名称点击定位功能

#### Watchlist 统计卡片
- 实时统计面板
- 点击过滤功能

### 3. 量化回测 (`/quant-backtest`)

#### 入场条件系统
- **基础条件**：6个扩展指标字段
  - 斜率 `slope_2m`
  - 动量 `momentum_5m`
  - 波动率 `volatility_10m`
  - RSI `rsi_14`
  - 突破强度 `breakout_strength`
  - 趋势一致性 `trend_consistency`
- **条件组功能**：
  - 组内 AND / 组间 OR
  - 支持嵌套子条件组
  - 复杂逻辑：`(A AND B) OR (C AND D)`

#### 回测引擎
- **两阶段查询**：入场信号 + 止盈止损判定
- **三种收益计算方式**：compound(复利) / average(平均) / curve(曲线)
- **时间线模式**：信号串行触发，更接近真实交易
- **价格偏移功能**：支持固定金额和百分比两种模式

#### 回测结果管理
- MySQL 持久化存储（`result_data` JSON列）
- Redis 热缓存（1天过期）
- 过期记录自动回填参数，支持一键重跑
- 最近记录按盈利率倒序展示
- 历史记录完整恢复参数 + 列表显示更多详情

#### 方案管理
- 保存/加载入场条件方案（MySQL持久化）
- 支持回测参数覆盖
- 方案状态记忆（is_active）
- 智能降级（同名覆盖而非重复添加）

#### 量化选债
- 实时信号跟踪
- 历史命中记录（MySQL存储）
- 今日命中次数动态计算
- 区间回测与智能缓存
- 统一核心引擎（quant_screen_core）

### 4. 个人中心 (`/profile`)

#### 待办事项管理
- **关键词搜索**：实时筛选 + 高亮显示
- **日期定位**：匹配项按日期分组展示
- **快捷操作**：点击切换完成/未完成
- **状态筛选**：全部/已完成/未完成/逾期/暂缓
- **优先级标记**：高/中/低

#### 日志系统
- 每日日志自动归档
- 日历视图快速跳转
- 情绪追踪与统计
- 日志内容定位功能

#### 交易规则管理
- 拖拽排序
- 分类管理
- 规则编辑/删除

### 5. 分析中心

#### 涨停分析 (`/ztb-analysis`)
- 涨停股票列表 + 市场板块筛选
- 涨停时段分布（竞价/早盘/午盘/尾盘）
- 个股详情面板（原因/预期/延续性）
- 买点候选与量化选债共用卡片tab切换

#### 新闻分析 (`/news-analysis`)
- DeepSeek AI 深度分析
- 消息大小智能计算（重大/大/中/小）
- 热点板块排行
- 当日统计面板
- 详情面板（AI评分、板块/概念/个股关联）

#### 公告分析 (`/notice-analysis`)
- 公告列表展示与筛选
- 当日统计：总公告、利好、利空、中性
- 风险等级标记（高/中/低）
- 公告详情查看

#### 领域分析 (`/domain-analysis`)
- 领域事件列表展示
- 当日统计：总事件、利好、利空、重大
- 热点板块排行
- 详情面板（事件描述、原因分析、深度分析、AI评分）

### 6. 数据采集

#### 基础采集 (16个任务)
- 涨停板数据、涨停炸板数据、指数宽基
- 今日龙虎榜、融资融券、公司动态
- 历史龙虎榜、通达信风险
- 同花顺行业、同花顺行业成分
- Baostock数据、问财基础数据、问财热股数据
- 可转债base、可转债daily、板块概念

#### 消息采集 (10个任务)
- 财经早餐、全球快讯、财联社历史等

#### 风险采集 (4个任务)
- 问财风险-日、问财风险-年、公告风险、Akshare风险

#### DeepSeek AI分析 (5个任务)
- 领域事件分析、财联社数据分析、综合数据分析
- 涨停板数据分析、公告分析

---

## 技术架构

### 后端技术栈
| 组件 | 用途 |
|------|------|
| Python 3.11 | 主开发语言 |
| Flask | Web框架 |
| SQLAlchemy | ORM |
| MySQL 8.0 | 主数据库 |
| Redis | 缓存 + 分布式锁 |
| DeepSeek API | AI分析引擎 |
| APScheduler | 定时任务 |

### 前端技术栈
| 组件 | 用途 |
|------|------|
| Vanilla JS (ES6+) | 主逻辑 |
| CSS Grid/Flexbox | 布局 |
| ECharts | 图表可视化 |
| Fetch API | 数据交互 |

### 核心目录结构
```
gs2026/
├── src/gs2026/dashboard2/          # Dashboard2 主项目
│   ├── app.py                      # Flask 入口
│   ├── routes/                     # API 路由
│   │   ├── monitor.py              # 监控数据路由
│   │   ├── anomaly.py              # 盘中异动路由
│   │   ├── backtest.py             # 量化回测路由
│   │   ├── profile.py              # 个人中心路由
│   │   ├── analysis_center.py      # 涨停分析路由
│   │   ├── news.py                 # 新闻分析路由
│   │   ├── notice_analysis.py      # 公告分析路由
│   │   └── domain_analysis.py      # 领域分析路由
│   ├── services/                   # 服务层
│   │   ├── backtest_bond.py        # 回测核心逻辑
│   │   ├── quant_screen_core.py    # 量化筛选核心
│   │   ├── backtest_cache.py       # 回测缓存管理
│   │   ├── news_service.py         # 新闻服务
│   │   ├── notice_analysis_service.py  # 公告分析服务
│   │   ├── domain_analysis_service.py  # 领域分析服务
│   │   └── ztb_analysis_service.py     # 涨停分析服务
│   ├── templates/                  # HTML 模板
│   │   ├── monitor.html            # 监控页面
│   │   ├── anomaly.html            # 盘中异动页面
│   │   ├── quant_backtest.html     # 量化回测页面
│   │   ├── profile.html            # 个人中心页面
│   │   ├── analysis_center.html    # 涨停分析页面
│   │   ├── news.html               # 新闻分析页面
│   │   ├── notice_analysis.html    # 公告分析页面
│   │   └── domain_analysis.html    # 领域分析页面
│   └── static/                     # 静态资源
├── src/gs2026/analysis/            # AI 分析模块
│   └── worker/
│       ├── message/deepseek/       # DeepSeek分析处理器
│       │   ├── combine_collection.py
│       │   └── prompts.py          # Prompt构建函数
│       └── realtime/               # 实时分析
│           ├── anomaly_analyzer.py     # 异动分析器
│           ├── anomaly_correlator.py   # 关联分析
│           └── anomaly_potential.py    # 潜力挖掘
├── migrations/                     # 数据库迁移
└── docs/                           # 项目文档
```

---

## 数据库核心表

### 回测相关
```sql
-- 回测历史记录
CREATE TABLE backtest_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    backtest_id VARCHAR(32) UNIQUE,  -- 哈希ID
    scheme_name VARCHAR(100),
    start_date DATE,
    end_date DATE,
    conditions_json JSON,            -- 入场条件
    result_data JSON,                -- 完整结果
    profit_rate DECIMAL(10,4),
    total_trades INT,
    win_rate DECIMAL(5,2),
    max_drawdown DECIMAL(10,4),
    avg_duration_sec INT,            -- 平均持仓时长
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 量化选债方案
CREATE TABLE quant_screen_schemes (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    conditions_json JSON,
    take_profit_pct DECIMAL(5,2),
    stop_loss_pct DECIMAL(5,2),
    max_hold_time INT,
    price_offset DECIMAL(10,4),
    offset_mode VARCHAR(20),           -- 'fixed' / 'percent'
    return_calc_method VARCHAR(20),    -- 'compound' / 'average' / 'curve'
    time_start TIME,
    time_end TIME,
    is_active TINYINT DEFAULT 1,
    use_backtest TINYINT DEFAULT 1,
    use_realtime TINYINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 量化选债命中记录
CREATE TABLE quant_screen_hits (
    id INT PRIMARY KEY AUTO_INCREMENT,
    scheme_id INT,
    bond_code VARCHAR(20),
    bond_name VARCHAR(100),
    entry_price DECIMAL(10,4),
    entry_time TIME,
    hit_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 盘中异动相关
```sql
-- 异动主线表
CREATE TABLE stock_anomaly_mainline (
    id INT PRIMARY KEY AUTO_INCREMENT,
    trading_date DATE,
    name VARCHAR(100),
    confidence DECIMAL(5,2),
    stock_count INT,
    mainline_summary JSON,           -- 主线综合分析（AI合成）
    synthesis_level VARCHAR(20),       -- formation/confirmed
    synthesis_time TIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 异动股票表
CREATE TABLE stock_anomaly (
    id INT PRIMARY KEY AUTO_INCREMENT,
    trading_date DATE,
    code VARCHAR(20),
    name VARCHAR(100),
    change_pct DECIMAL(10,4),
    amount DECIMAL(20,2),
    ai_analysis JSON,                -- AI分析结果
    mainline_name VARCHAR(100),
    role_in_mainline VARCHAR(50),      -- 龙头/跟风/补涨
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 分析中心相关
```sql
-- 新闻分析
CREATE TABLE analysis_news_detail_2026 (
    id INT PRIMARY KEY AUTO_INCREMENT,
    news_id VARCHAR(50),
    title VARCHAR(500),
    content TEXT,
    ai_score INT,
    ai_analysis JSON,
    message_size VARCHAR(20),        -- 重大/大/中/小
    message_type VARCHAR(20),          -- 利好/利空/中性
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 公告分析
CREATE TABLE analysis_notice_detail_2026 (
    id INT PRIMARY KEY AUTO_INCREMENT,
    notice_id VARCHAR(50),
    title VARCHAR(500),
    content TEXT,
    ai_score INT,
    risk_level VARCHAR(20),            -- 高/中/低
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 领域分析
CREATE TABLE analysis_domain_detail_2026 (
    id INT PRIMARY KEY AUTO_INCREMENT,
    event_id VARCHAR(50),
    title VARCHAR(500),
    description TEXT,
    ai_score INT,
    message_size VARCHAR(20),
    message_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 涨停分析
CREATE TABLE analysis_ztb_detail_2026 (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(20),
    name VARCHAR(100),
    ztb_time TIME,
    ztb_reason TEXT,
    ai_analysis JSON,
    market_board VARCHAR(50),          -- 沪深主板/科创板/创业板
    has_lhb TINYINT,                   -- 是否有龙虎榜
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 快速启动

### 启动 Dashboard2
```bash
cd F:\pyworkspace2026\gs2026
python start_dashboard2_flask.py
```

### 访问地址
- 首页: http://localhost:8080
- 监控: http://localhost:8080/monitor
- 盘中异动: http://localhost:8080/anomaly
- 量化回测: http://localhost:8080/quant-backtest
- 个人中心: http://localhost:8080/profile
- 涨停分析: http://localhost:8080/ztb-analysis
- 新闻分析: http://localhost:8080/news-analysis
- 公告分析: http://localhost:8080/notice-analysis
- 领域分析: http://localhost:8080/domain-analysis

---

## 完整更新日志

### v2026.7.13 - 市场主线分析 + 条件组 + 待办搜索
- ✅ 市场主线综合分析系统（里程碑AI合成 + 动态追踪）
- ✅ 量化回测条件组功能（组内AND/组间OR + 嵌套子条件组）
- ✅ 6个扩展指标字段（斜率/动量/波动率/RSI/突破强度/趋势一致性）
- ✅ 回测结果MySQL持久化（result_data JSON列）
- ✅ 过期记录自动回填参数，支持一键重跑
- ✅ 待办关键词搜索（高亮 + 日期定位 + 快捷操作）
- ✅ 过滤器面板化改造（股票/债券排行）
- ✅ 斜率指标体系（加权斜率/变化率/加速度 + 大盘/个券共振）

### v2026.7.10 - 量化选债优化
- ✅ 量化选债历史数据回放测试
- ✅ 统一核心引擎（quant_screen_core）
- ✅ 今日命中次数动态计算
- ✅ 区间回测与智能缓存
- ✅ 方案管理API集成（MySQL持久化）

### v2026.7.5 - 债券排行增强
- ✅ 债券排行列配置系统
- ✅ 金额排名字段（amount_rank）
- ✅ 1分钟字段计算（min1_change_pct/min1_amount）
- ✅ 历史日期 + 时间点查询支持

### v2026.6.28 - 量化回测基础
- ✅ 债券量化回测功能（两阶段查询 + 止盈止损）
- ✅ 三种收益计算方式（compound/average/curve）
- ✅ 价格偏移功能（固定金额/百分比）
- ✅ 时间线模式（信号串行触发）

### v2026.6.20 - 分析中心完整功能
- ✅ 涨停分析（市场板块筛选 + 时段分布）
- ✅ 新闻分析（热点板块 + 消息大小计算）
- ✅ 公告分析（风险等级 + 当日统计）
- ✅ 领域分析（事件分析 + 深度AI评分）

### v2026.6.10 - 监控功能增强
- ✅ 股票/债券排行时间轴查询
- ✅ 行业板块排行折叠功能
- ✅ 股债联动监控
- ✅ 大盘趋势指标

### v2026.5.30 - 盘中异动基础
- ✅ 异动股票AI分析
- ✅ 主线归属判定
- ✅ Watchlist统计卡片
- ✅ 股票代码/名称点击定位

### v2026.5.15 - Dashboard2基础架构
- ✅ Flask应用框架
- ✅ Redis连接池优化
- ✅ 进程管理（ProcessManager）
- ✅ 数据采集面板模块化

### v2026.4.15 - 分析中心上线
- ✅ 四大分析模块（涨停/新闻/公告/领域）
- ✅ DeepSeek AI集成
- ✅ 消息大小/类型智能计算
- ✅ 热点板块排行

---

## 开发团队

- **项目**: GS2026 量化投研平台
- **版本**: v2026.7.13
- **主要开发**: AI Assistant

## 许可证

私有项目
