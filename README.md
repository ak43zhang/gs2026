# GS2026 Dashboard2 项目文档

## 项目概述

GS2026 Dashboard2 是一个数据采集和监控面板，支持股票、债券、行业数据的采集和AI分析。

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

### 3. 数据分析 (新增)
- **DeepSeek AI分析** (5个任务)
  - 领域事件分析 (支持日期列表参数)
  - 财联社数据分析
  - 综合数据分析
  - 涨停板数据分析
  - 公告分析

## 技术栈

- **后端**: Python Flask + Redis
- **前端**: JavaScript (ES6+) + CSS Grid/Flexbox
- **数据库**: MySQL
- **进程管理**: 自定义ProcessManager + Redis分布式锁

## 项目结构

```
gs2026/
├── src/gs2026/dashboard2/          # Dashboard2主项目
│   ├── app.py                      # Flask应用入口
│   ├── routes/                     # API路由
│   │   ├── collection.py           # 数据采集API
│   │   ├── analysis.py             # 数据分析API
│   │   └── analysis_modules.py     # 分析模块配置
│   ├── static/                     # 静态资源
│   │   ├── css/                    # 样式文件
│   │   └── js/                     # JavaScript
│   │       ├── components/         # UI组件
│   │       ├── modules/            # 管理器
│   │       └── pages/              # 页面脚本
│   └── templates/                  # HTML模板
├── src/gs2026/dashboard/           # 原版Dashboard
│   └── services/
│       └── process_manager.py      # 进程管理器
├── src/gs2026/analysis/            # AI分析脚本
│   └── worker/message/deepseek/    # DeepSeek分析
├── docs/                           # 项目文档
└── sql/                            # SQL脚本
```

## 启动方式

### 启动 Dashboard2
```bash
cd F:\pyworkspace2026\gs2026
.\.venv\Scripts\python.exe -m gs2026.dashboard2.app
```

访问: http://localhost:8080

### 启动原版 Dashboard (如需)
```bash
cd F:\pyworkspace2026\gs2026
.\.venv\Scripts\python.exe -m gs2026.dashboard.app
```

## 主要功能特性

### 1. 进程管理
- Redis分布式锁防止重复处理
- 自动进程保活
- 实时状态监控

### 2. 任务调度
- 支持立即执行和定时执行
- 批量任务管理
- 任务参数配置

### 3. 前端特性
- 模块化组件设计
- 实时状态更新
- 编辑锁定机制（防止刷新丢失参数）

## 配置说明

### 分析模块配置
配置文件: `src/gs2026/dashboard2/routes/analysis_modules.py`

```python
ANALYSIS_MODULES = {
    'deepseek': {
        'name': 'DeepSeek AI分析',
        'icon': '🤖',
        'tasks': {
            'event_driven': {
                'name': '领域事件分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_event_driven.py',
                'function': 'analysis_event_driven',
                'params': [
                    {
                        'name': 'date_list',
                        'type': 'date_list',
                        'label': '分析日期列表',
                        'required': True
                    }
                ]
            }
        }
    }
}
```

## 已知问题

### Bug #1: 数据分析启动报错
- **状态**: 🔴 待修复
- **时间**: 2026-03-27
- **描述**: 数据分析模块点击启动按钮时报错
- **详情**: 见 `docs/dashboard2_analysis_design.md`

## 开发记录

### 2026-03-27
- ✅ 数据分析模块开发完成
- ✅ 日期列表参数类型实现
- ✅ 编辑锁定机制优化
- ✅ 导航栏样式统一
- 🐛 数据分析启动报错（待修复）

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
