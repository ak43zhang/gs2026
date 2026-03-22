# 变更日志

## [2026.1.0] - 2026-03-22

### 新增

- **项目初始化** - 基于 gs2025 重构的企业级股票数据分析系统
- **统一配置管理模块 (config/)** - 支持 YAML 配置和环境变量覆盖
- **核心功能模块 (core/)** - 应用主类、自定义异常、事件系统
- **采集模块 (collection/)**
  - base/ - 基础数据采集（指数、龙虎榜、融资融券等）
  - news/ - 新闻数据采集
  - other/ - 其他数据采集
  - risk/ - 风险数据采集
- **分析模块 (analysis/)** - AI分析器（DeepSeek、百度）
- **监控模块 (monitor/)** - 监控服务、通知服务
- **工具模块 (utils/)**
  - config_util.py - 配置管理
  - decorators_util.py - 日志装饰器（自动配置）
  - email_util.py - 邮件工具
  - mysql_util.py - MySQL工具
  - account_pool_util.py - 账号池管理
- **常量模块 (constants/)** - 市场类型、SQL语句、浏览器路径等
- **工具模块 (tools/)** - 文本过滤、数据验证
- **命令行接口 (cli.py)** - CLI入口
- **完整文档** - README、USAGE、ARCHITECTURE、DECORATORS_GUIDE

### 特性

- **零配置日志** - 使用 `@log_decorator` 自动配置日志
- **统一导入模式** - 所有模块使用一致的导入方式
- **环境变量支持** - 所有配置支持环境变量覆盖
- **类型安全** - 完整的类型注解
- **模块化设计** - 清晰的模块划分
- **Google风格文档字符串**
- **可扩展架构** - 易于添加新数据源和分析器

### 改进

- 简化常量管理模块（单文件）
- 日志装饰器自动配置，无需手动设置
- 统一变量命名（`mysql_tool`）
- 统一配置获取方式（`config_util.get_config`）
- 批量修复所有导入语句

## [2026.1.1] - 2026-03-22

### 新增

- **通用任务运行器 (task_runner.py)** - 封装后台线程运行、异常告警、优雅退出的统一模块
  - `run_daemon_task()` - 一行代码启动守护任务，自动处理线程、异常、邮件告警
  - 支持前台/后台运行模式切换
  - 支持资源清理回调函数
- **企业级注释** - 为 deepseek 目录下所有分析模块添加完整文档
  - 模块级 docstring（用途、核心功能、依赖关系）
  - Google 风格函数 docstring（Args、Returns、Raises、Example）
  - 完整类型注解
  - 关键业务逻辑行内注释

### 优化

- **代码重构** - 将 12 个分析/采集脚本的重复代码替换为 `run_daemon_task`
  - 改造文件：baidu_analysis_news_*.py (5个)、deepseek_analysis_news_*.py (2个)、news/*.py (5个)
  - 每文件减少 15-20 行重复代码（threading + try/except + 邮件告警）
  - 修复 `threading.Thread(target=func(args))` bug（会立即执行而非在线程中执行）
- **日志输出统一** - 将所有 `print()` 替换为 `logger.info/error/warning`，统一使用 loguru 日志
- **类型注解完善** - 为核心模块添加完整的类型注解
  - `base_collection.py` - 所有函数添加返回类型和参数类型
  - `baostock_collection.py` - 所有函数添加类型注解
  - `zt_collection.py` - 所有函数添加类型注解
  - `mysql_util.py` - 所有方法添加类型注解
  - `email_util.py` - 所有方法添加类型注解
  - `log_util.py` - 所有函数添加类型注解
  - `string_enum.py` - 添加模块文档字符串
  - `display_config.py` - 添加类型注解
  - `pandas_display_config.py` - 修复 `NoReturn` 类型误用为 `None`
  - `redis_util.py` - 将 `print()` 替换为 `logger`，添加类型注解
- **变量命名统一** - 将 `mysql_util` 统一改为 `mysql_tool`，避免与模块名冲突

### 依赖

- Python >= 3.10
- pandas >= 2.2.0
- sqlalchemy >= 2.0.0
- akshare >= 1.18.0
- playwright >= 1.58.0
- loguru >= 0.7.0
