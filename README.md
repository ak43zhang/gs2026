# GS2026 股票数据分析系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

GS2026 是一个专业的股票数据采集与分析系统，支持多数据源采集、AI智能分析、实时监控等功能。

## ✨ 核心特性

- 📊 **多数据源采集** - 支持 AKShare、Baostock、Tushare、问财等数据源
- 🤖 **AI智能分析** - 集成 DeepSeek AI 进行涨停复盘分析
- 📈 **实时数据监控** - 实时监控股票行情、板块热度、资金流向
- 🔔 **智能告警通知** - 邮件通知异常情况
- 🛡️ **风险数据管理** - 全面采集风险信息，辅助投资决策
- 📝 **统一日志管理** - 自动日志记录，支持日志装饰器

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/yourusername/gs2026.git
cd gs2026

# 安装依赖
pip install -e .

# 或使用开发模式安装
pip install -e ".[dev]"
```

### 配置

1. 复制配置文件模板：
```bash
cp configs/settings.example.yaml configs/settings.yaml
```

2. 编辑 `configs/settings.yaml`，配置数据库连接：
```yaml
database:
  host: localhost
  port: 3306
  user: root
  password: your_password
  name: gs2026
```

3. 或使用环境变量：
```bash
export GS2026_DATABASE_HOST=localhost
export GS2026_DATABASE_PORT=3306
export GS2026_DATABASE_USER=root
export GS2026_DATABASE_PASSWORD=your_password
export GS2026_DATABASE_NAME=gs2026
```

### 运行

```python
from gs2026.collection.base import base_collection

# 采集基础数据
base_collection.get_base_collect("2026-03-20", "2026-03-20")
```

## 📁 项目结构

```
gs2026/
├── src/gs2026/              # 源代码
│   ├── collection/          # 数据采集模块
│   │   ├── base/            # 基础数据采集
│   │   ├── news/            # 新闻数据采集
│   │   ├── other/           # 其他数据采集
│   │   └── risk/            # 风险数据采集
│   ├── analysis/            # 数据分析模块
│   ├── monitor/             # 监控服务
│   ├── utils/               # 工具模块
│   ├── constants/           # 常量定义
│   └── core/                # 核心功能
├── configs/                 # 配置文件
├── docs/                    # 文档
├── tests/                   # 测试
└── logs/                    # 日志
```

## 📖 文档

- [使用手册](docs/USAGE.md) - 详细使用说明
- [架构设计](docs/ARCHITECTURE.md) - 系统架构文档
- [装饰器指南](docs/DECORATORS_GUIDE.md) - 日志装饰器使用
- [变更日志](docs/CHANGELOG.md) - 版本更新记录

## 🔧 依赖

- Python >= 3.10
- pandas >= 2.2.0
- sqlalchemy >= 2.0.0
- akshare >= 1.18.0
- playwright >= 1.58.0
- loguru >= 0.7.0

完整依赖见 `requirements.txt`

## 🛠️ 开发

```bash
# 安装开发依赖
pip install -r requirements-dev.txt
# 或
pip install -e ".[dev]"

# 代码格式化
black src/
isort src/

# 类型检查
mypy src/gs2026

# 运行测试
pytest
```

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系

如有问题，请联系：m17600700886@163.com
