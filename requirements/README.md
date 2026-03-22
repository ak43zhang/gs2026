# Requirements 依赖管理说明

## 文件说明

| 文件 | 用途 | 适用场景 |
|------|------|----------|
| `base.txt` | 核心依赖 | 所有环境必需 |
| `dev.txt` | 开发工具 | 开发环境 |
| `test.txt` | 测试框架 | 测试环境 |
| `docs.txt` | 文档工具 | 文档构建 |
| `prod.txt` | 生产优化 | 生产环境 |
| `local.txt` | 本地开发 | 本地调试 |

## 安装方式

### 基础安装（最小依赖）
```bash
pip install -r requirements/base.txt
```

### 开发环境
```bash
pip install -r requirements/dev.txt
```

### 测试环境
```bash
pip install -r requirements/test.txt
```

### 本地开发（完整）
```bash
pip install -r requirements/local.txt
```

### 生产环境
```bash
pip install -r requirements/prod.txt
```

### 文档构建
```bash
pip install -r requirements/docs.txt
```

## 依赖分类

### base.txt - 核心依赖
- 数据处理: pandas, numpy, pyarrow
- 数据采集: akshare, baostock, tushare
- HTTP请求: requests, httpx, aiohttp
- 数据库: SQLAlchemy, mysql-connector-python
- 缓存: redis
- 浏览器: playwright, selenium
- 配置: pydantic, python-dotenv

### dev.txt - 开发工具
- 代码格式化: black, isort
- 代码检查: flake8, pylint, mypy
- 安全检查: bandit
- 调试: ipdb, ipython
- 性能分析: memory-profiler

### test.txt - 测试框架
- 测试框架: pytest, pytest-asyncio
- 覆盖率: pytest-cov, coverage
- 模拟数据: faker, factory-boy
- 性能测试: locust

### docs.txt - 文档工具
- 文档生成: mkdocs, mkdocs-material
- API文档: mkdocstrings

### prod.txt - 生产优化
- WSGI服务器: gunicorn, uvicorn
- 监控: prometheus-client, sentry-sdk
- 任务队列: celery

### local.txt - 本地开发
- 包含: dev.txt + test.txt
- Jupyter: jupyter, jupyterlab
- 可视化: matplotlib, seaborn, plotly
- 交互式: streamlit, gradio
