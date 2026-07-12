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

#### 债券上攻排行
- 可转债实时涨幅监控
- 斜率指标体系：加权斜率、变化率、加速度
- 大盘/个券共振检测

#### 行业板块排行
- 行业涨跌幅实时监控
- 历史日期回溯支持

#### 大盘信号监控
- 加权斜率指标 `mkt_weighted_slope_2m`
- 变化率 `mkt_change_1m_pct`
- 价格加速度 `mkt_price_acceleration`

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

### 3. 量化回测 (`/quant-backtest`)

#### 入场条件系统
- **基础条件**：6个扩展指标字段（斜率、动量、波动率、RSI、突破强度、趋势一致性）
- **条件组功能**：
  - 组内 AND / 组间 OR
  - 支持嵌套子条件组
  - 复杂逻辑：`(A AND B) OR (C AND D)`

#### 回测结果管理
- MySQL 持久化存储（`result_data` JSON列）
- Redis 热缓存（1天过期）
- 过期记录自动回填参数，支持一键重跑
- 最近记录按盈利率倒序展示

#### 方案管理
- 保存/加载入场条件方案
- 支持回测参数覆盖

### 4. 个人中心 (`/profile`)

#### 待办事项管理
- **关键词搜索**：实时筛选 + 高亮显示
- **日期定位**：匹配项按日期分组展示
- **快捷操作**：点击切换完成/未完成
- **状态筛选**：全部/已完成/未完成/逾期/暂缓

#### 日志系统
- 每日日志自动归档
- 日历视图快速跳转
- 情绪追踪与统计

### 5. 分析中心

#### 涨停分析 (`/ztb-analysis`)
- 涨停股票列表 + 市场板块筛选
- 涨停时段分布（竞价/早盘/午盘/尾盘）
- 个股详情面板（原因/预期/延续性）

#### 新闻/公告/领域分析
- DeepSeek AI 深度分析
- 消息大小智能计算（重大/大/中/小）
- 热点板块排行
- 当日统计面板

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
│   │   └── profile.py              # 个人中心路由
│   ├── services/                   # 服务层
│   │   ├── backtest_bond.py        # 回测核心逻辑
│   │   ├── quant_screen_core.py    # 量化筛选核心
│   │   └── backtest_cache.py       # 回测缓存管理
│   ├── templates/                  # HTML 模板
│   │   ├── monitor.html            # 监控页面
│   │   ├── anomaly.html            # 盘中异动页面
│   │   ├── quant_backtest.html     # 量化回测页面
│   │   └── profile.html            # 个人中心页面
│   └── static/                     # 静态资源
├── src/gs2026/analysis/            # AI 分析模块
│   └── worker/realtime/            # 实时分析
│       ├── anomaly_analyzer.py     # 异动分析器
│       ├── anomaly_correlator.py   # 关联分析
│       └── anomaly_potential.py    # 潜力挖掘
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
    result_data JSON,                -- 完整结果（新增）
    profit_rate DECIMAL(10,4),
    total_trades INT,
    win_rate DECIMAL(5,2),
    max_drawdown DECIMAL(10,4),
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

---

## 近期重大更新 (v2026.7.13)

### 市场主线综合分析系统
- ✅ 里程碑触发AI合成（formation/confirmed）
- ✅ 主线动态追踪 + 发展时间线
- ✅ 阶段判定：发酵期/扩散期/高潮期/分歧期
- ✅ 展示维度：驱动逻辑/催化事件/持续性

### 量化回测条件组
- ✅ 基础条件 + 条件组双层架构
- ✅ 组内AND、组间OR逻辑
- ✅ 嵌套子条件组支持
- ✅ 6个扩展指标字段（JSON存储）

### 回测持久化
- ✅ MySQL `result_data` JSON列存储完整结果
- ✅ Redis过期后自动回退查MySQL
- ✅ 过期记录自动回填参数，支持一键重跑

### 待办搜索
- ✅ 关键词实时搜索 + 高亮显示
- ✅ 日期定位：按日期分组展示
- ✅ 快捷操作：点击切换完成状态

### 过滤器面板化
- ✅ 股票/债券排行过滤器改为面板模式
- ✅ 配置数组驱动，支持扩展
- ✅ 修复历史日期下date参数缺失问题

---

## 开发团队

- **项目**: GS2026 量化投研平台
- **版本**: v2026.7.13
- **主要开发**: AI Assistant

## 许可证

私有项目
