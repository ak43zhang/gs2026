# GS2026 架构设计文档

## 项目概述

GS2026 是一个专业的股票数据采集与分析系统，采用现代化的 Python 项目架构。

## 目录结构

```
gs2026/
├── docs/                    # 文档模块
│   ├── ARCHITECTURE.md      # 架构设计文档
│   ├── CHANGELOG.md         # 变更日志
│   ├── DECORATORS_GUIDE.md  # 装饰器使用手册
│   ├── README.md            # 项目简介
│   └── USAGE.md             # 使用手册
│
├── src/gs2026/              # 源代码
│   ├── __init__.py
│   ├── __version__.py       # 版本信息
│   ├── cli.py               # 命令行接口
│   │
│   ├── analysis/            # 🔍 分析模块
│   │   ├── worker/
│   │   │   └── message/
│   │   │       ├── baidu/       # 百度分析
│   │   │       └── deepseek/    # DeepSeek AI分析
│   │   ├── base.py          # 分析器基类
│   │   └── ai_analyzer.py   # AI分析器
│   │
│   ├── collection/          # 📥 采集模块
│   │   ├── base/            # 基础数据采集
│   │   │   ├── base_collection.py
│   │   │   ├── baostock_collection.py
│   │   │   ├── bk_gn_collection.py
│   │   │   ├── wencai_collection.py
│   │   │   └── zt_collection.py
│   │   ├── news/            # 新闻数据采集
│   │   ├── other/           # 其他数据采集
│   │   └── risk/            # 风险数据采集
│   │
│   ├── constants/           # 📋 常量定义
│   │   └── __init__.py      # 所有常量
│   │
│   ├── core/                # 🔧 核心功能
│   │   ├── application.py   # 应用主类
│   │   ├── exceptions.py    # 自定义异常
│   │   └── events.py        # 事件系统
│   │
│   ├── monitor/             # 🏢 监控服务
│   │   ├── monitor_service.py
│   │   └── notification_service.py
│   │
│   ├── tools/               # 🛠️ 工具模块
│   │   ├── filters.py       # 文本过滤
│   │   └── validators.py    # 数据验证
│   │
│   └── utils/               # 🔨 通用工具
│       ├── account_pool_util.py
│       ├── config_util.py   # 配置管理
│       ├── decorators_util.py  # 装饰器
│       ├── email_util.py    # 邮件工具
│       ├── mysql_util.py    # MySQL工具
│       ├── string_util.py   # 字符串工具
│       └── task_runner.py   # 通用任务运行器（守护线程封装）
│
├── tests/                   # 测试模块
├── configs/                 # 配置文件
├── logs/                    # 日志目录
├── requirements.txt         # 生产环境依赖
└── requirements-dev.txt     # 开发环境依赖
```

## 模块说明

### 1. constants/ - 常量定义

集中管理所有常量，包括：
- 市场类型（SH/SZ/BJ）
- 股票类型（主板/创业板/科创板）
- SQL查询语句
- 浏览器路径
- 关键词集合

```python
from gs2026.constants import MARKET_SH, SQL_STOCK_MAIN_GEM
```

### 2. utils/ - 通用工具

#### config_util.py - 配置管理
- 支持 YAML 配置文件
- 环境变量覆盖
- 分层配置获取

```python
from gs2026.utils.config_util import get_config, cfg

# 获取配置
value = get_config("database.host", "localhost")

# 快捷访问
db_port = cfg.db_port()
```

#### decorators_util.py - 装饰器
- 日志装饰器（自动配置）
- 重试装饰器
- 计时装饰器
- 类日志装饰器

```python
from gs2026.utils.decorators_util import log_decorator

@log_decorator(log_level="INFO", log_args=True)
def my_function():
    pass
```

#### email_util.py - 邮件工具
- 联系人管理
- 邮件模板
- 批量发送

#### mysql_util.py - MySQL工具
- 数据库连接管理
- 表操作
- 数据操作

#### task_runner.py - 通用任务运行器
- 后台守护线程封装
- 统一异常处理和邮件告警
- 资源清理回调支持

```python
from gs2026.utils.task_runner import run_daemon_task

# 启动守护任务（自动处理线程、异常、告警）
run_daemon_task(target=my_task_func, args=(10,))
```

### 3. collection/ - 数据采集

#### base/ - 基础数据采集
- `base_collection.py` - 指数、龙虎榜、融资融券等
- `baostock_collection.py` - Baostock数据源
- `bk_gn_collection.py` - 板块概念数据
- `wencai_collection.py` - 问财数据
- `zt_collection.py` - 涨停数据

#### news/ - 新闻数据采集
- 财联社新闻
- 证券时报新闻
- 其他财经新闻

#### risk/ - 风险数据采集
- 问询函、公告风险
- 历史风险数据

### 4. analysis/ - 数据分析

#### worker/message/deepseek/ - DeepSeek AI分析
- AI涨停复盘分析
- 事件驱动分析

#### worker/message/baidu/ - 百度分析
- 新闻分析
- 公告分析

### 5. tools/ - 工具模块

#### filters.py - 文本过滤
- 敏感词检测
- 风险关键词检测
- 国家/官方关键词

#### validators.py - 数据验证
- 股票代码验证
- 市场类型判断

### 6. core/ - 核心功能

#### application.py - 应用主类
- 应用生命周期管理
- 初始化配置

#### exceptions.py - 自定义异常
- 统一的异常体系

#### events.py - 事件系统
- 事件总线
- 事件订阅/发布

### 7. monitor/ - 监控服务

#### monitor_service.py - 实时监控
- 数据采集监控
- 性能监控

#### notification_service.py - 通知服务
- 邮件通知
- 告警管理

## 设计原则

1. **单一职责** - 每个模块只负责一项功能
2. **开闭原则** - 对扩展开放，对修改关闭
3. **依赖倒置** - 依赖抽象而非具体实现
4. **配置分离** - 配置与代码分离
5. **DRY原则** - 不要重复自己

## 使用示例

### 配置管理

```python
from gs2026.utils.config_util import get_config

# 获取数据库配置
db_host = get_config("database.host", "localhost")
db_port = get_config("database.port", 3306)
```

### 数据采集

```python
from gs2026.collection.base import base_collection

# 采集基础数据
base_collection.get_base_collect("2026-03-20", "2026-03-20")
```

### 使用装饰器

```python
from gs2026.utils.decorators_util import log_decorator, retry

@log_decorator(log_level="INFO", log_args=True)
@retry(max_attempts=3, delay=1.0)
def fetch_data(url):
    return requests.get(url).json()
```

### 常量使用

```python
from gs2026.constants import MARKET_SH, get_market_by_code

# 获取市场类型
market = get_market_by_code("600001")  # "SH"
```

## 扩展方式

### 添加新的采集器

1. 在 `collection/` 下创建新文件
2. 使用统一的导入模式
3. 添加 `@log_decorator` 装饰器

### 添加新的分析器

1. 在 `analysis/` 下创建新模块
2. 继承基类或实现分析函数
3. 集成到调度流程

## 配置文件

### settings.yaml 示例

```yaml
app:
  name: "GS2026"
  version: "2026.1.0"
  debug: false
  log_dir: "logs"
  log_level: "INFO"

database:
  host: "localhost"
  port: 3306
  user: "root"
  password: "password"
  name: "gs2026"

redis:
  host: "localhost"
  port: 6379
  db: 0
```

## 日志管理

日志自动配置，无需手动设置：

```python
from gs2026.utils.decorators_util import log_decorator

@log_decorator(log_level="INFO")
def my_function():
    # 自动记录日志
    pass
```

日志文件位置：`logs/gs2026_YYYYMMDD.log`

## 测试

```bash
# 运行测试
pytest

# 运行特定测试
pytest tests/test_decorators.py
```

## 部署

```bash
# 生产环境安装
pip install ".[prod]"

# 运行
python -m gs2026
```
