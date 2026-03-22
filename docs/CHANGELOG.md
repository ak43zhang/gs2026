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

### 优化

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
  - `pandas_display_config.py` - 添加类型注解
  - `redis_util.py` - 将 `print()` 替换为 `logger`，添加类型注解
- **变量命名统一** - 将 `mysql_util` 统一改为 `mysql_tool`，避免与模块名冲突

### 依赖

- Python >= 3.10
- pandas >= 2.2.0
- sqlalchemy >= 2.0.0
- akshare >= 1.18.0
- playwright >= 1.58.0
- loguru >= 0.7.0
