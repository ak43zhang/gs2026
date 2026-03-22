# GS2026 使用手册

## 目录

1. [快速开始](#快速开始)
2. [配置说明](#配置说明)
3. [数据采集](#数据采集)
4. [数据分析](#数据分析)
5. [日志装饰器](#日志装饰器)
6. [工具函数](#工具函数)
7. [常见问题](#常见问题)

---

## 快速开始

### 1. 安装

```bash
# 基础安装
pip install -e .

# 开发环境安装
pip install -e ".[dev,test]"

# 生产环境安装
pip install -e ".[prod]"
```

### 2. 配置

创建 `configs/settings.yaml`：

```yaml
# 应用配置
app:
  name: "GS2026"
  version: "2026.1.0"
  debug: false
  log_dir: "logs"
  log_level: "INFO"

# 数据库配置
database:
  host: "localhost"
  port: 3306
  user: "root"
  password: "your_password"
  name: "gs2026"

# Redis配置
redis:
  host: "localhost"
  port: 6379
  db: 0

# 采集配置
collection:
  sources:
    - akshare
    - baostock
  timeout: 30
  retry_times: 3

# 邮件配置
email:
  smtp_server: "smtp.163.com"
  smtp_port: 465
  sender: "your_email@163.com"
  password: "your_email_password"
```

### 3. 运行示例

```python
from gs2026.collection.base import base_collection
from gs2026.utils.config_util import get_config

# 获取配置
db_host = get_config("database.host", "localhost")
print(f"数据库主机: {db_host}")

# 采集数据
base_collection.get_base_collect("2026-03-20", "2026-03-20")
```

---

## 配置说明

### 环境变量

所有配置都支持通过环境变量覆盖：

```bash
# 格式: GS2026_<配置键>
export GS2026_DATABASE_HOST=192.168.1.100
export GS2026_DATABASE_PORT=3306
export GS2026_APP_DEBUG=true
```

### 配置优先级

1. 环境变量（最高优先级）
2. 配置文件
3. 默认值（最低优先级）

### 配置获取

```python
from gs2026.utils.config_util import get_config, cfg

# 方式1: 直接获取
value = get_config("database.host", "localhost")

# 方式2: 类型化获取
port = get_config("database.port", 3306)  # 返回整数
debug = get_config("app.debug", False)    # 返回布尔值

# 方式3: 快捷访问
db_host = cfg.db_host()
db_port = cfg.db_port()
```

---

## 数据采集

### 基础数据采集

```python
from gs2026.collection.base import base_collection

# 采集指定日期范围的数据
base_collection.get_base_collect("2026-03-20", "2026-03-20")

# 采集指数宽基行情
base_collection.zskj()

# 采集龙虎榜数据
base_collection.today_lhb("2026-03-20", "2026-03-20")

# 采集融资融券数据
base_collection.rzrq()
```

### 涨停数据采集

```python
from gs2026.collection.base import zt_collection

# 采集涨停数据
zt_collection.collect_ztb_query("2026-03-20", "2026-03-20")

# 采集炸板数据
zt_collection.collect_zt_zb_collection("2026-03-20", "2026-03-20")
```

### 板块概念采集

```python
from gs2026.collection.base import bk_gn_collection

# 采集板块概念数据
bk_gn_collection.bk_gn_collect("2026-03-20", "2026-03-20")
```

### 问财数据采集

```python
from gs2026.collection.base import wencai_collection

# 采集基础数据
wencai_collection.collect_base_query("2026-03-20", "2026-03-20")

# 采集热度数据
wencai_collection.collect_popularity_query("2026-03-20", "2026-03-20")
```

### Baostock数据采集

```python
from gs2026.collection.base import baostock_collection

# 采集股票历史数据
baostock_collection.get_baostock_collection("2026-03-20", "2026-03-20")
```

---

## 数据分析

### AI分析

```python
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven

# 定时执行分析
deepseek_analysis_event_driven.check_time_and_execute(
    target_date=datetime(2026, 3, 20, 17, 30),
    check_interval=60,
    execute_func=your_analysis_function,
    start_date="2026-03-20",
    end_date="2026-03-20"
)
```

---

## 日志装饰器

### 基本使用

```python
from gs2026.utils.decorators_util import log_decorator, timing

# 只需添加装饰器，无需配置
@log_decorator(log_level="INFO", log_args=True)
def my_function(x, y):
    return x + y

# 组合使用
@log_decorator(log_level="DEBUG", log_args=True, log_result=True)
@timing
def process_data(data):
    # 处理逻辑
    return result
```

### 类日志装饰器

```python
from gs2026.utils.decorators_util import class_logger

@class_logger(log_level="INFO")
class MyClass:
    def method1(self):
        pass
    
    def method2(self, x):
        return x * 2
```

### 重试装饰器

```python
from gs2026.utils.decorators_util import retry

@retry(max_attempts=3, delay=1.0)
def fetch_data(url):
    return requests.get(url).json()
```

---

## 工具函数

### 配置工具

```python
from gs2026.utils.config_util import get_config, cfg, reload_config

# 获取配置
value = get_config("key.subkey", default)

# 快捷访问
db_host = cfg.db_host()
db_port = cfg.db_port()

# 重新加载配置
reload_config()
```

### 邮件工具

```python
from gs2026.utils.email_util import (
    get_email_list,
    get_contact_by_email,
    get_email_template
)

# 获取邮箱列表
emails = get_email_list()

# 获取邮件模板
template = get_email_template("daily_report", date="2026-03-20")
```

### 数据库工具

```python
from gs2026.utils.mysql_util import MysqlTool
from gs2026.utils.config_util import get_config

url = get_config("common.url")
mysql_tool = MysqlTool(url)

# 删除表
mysql_tool.drop_mysql_table("table_name")

# 删除数据
mysql_tool.delete_data("DELETE FROM table WHERE condition")

# 检查表是否存在
exists = mysql_tool.check_table_exists("table_name")
```

### 常量

```python
from gs2026.constants import (
    MARKET_SH, MARKET_SZ,  # 市场类型
    STOCK_MAIN, STOCK_GEM,  # 股票类型
    SQL_STOCK_MAIN_GEM,  # SQL查询
    FIREFOX_1408, CHROME_1208,  # 浏览器路径
)

# 根据代码获取市场
from gs2026.constants import get_market_by_code
market = get_market_by_code("600001")  # "SH"
```

### 文本过滤

```python
from gs2026.tools import (
    contains_sensitive_word,
    is_risk_related,
    is_valid_stock_code
)

# 检查敏感词
if contains_sensitive_word(text):
    print("包含敏感词")

# 检查风险
if is_risk_related(text):
    print("包含风险信息")

# 验证股票代码
if is_valid_stock_code("600001"):
    print("有效代码")
```

---

## 常见问题

### Q1: 如何设置日志级别？

```python
# 在代码中设置
import os
os.environ["GS2026_APP_LOG_LEVEL"] = "DEBUG"

# 或在配置文件中
app:
  log_level: "DEBUG"
```

### Q2: 如何添加新的数据源？

1. 在 `collection/` 下创建新的采集模块
2. 继承基类或实现采集函数
3. 使用 `@log_decorator` 添加日志

### Q3: 如何配置定时任务？

```python
from datetime import datetime
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven

deepseek_analysis_event_driven.check_time_and_execute(
    target_date=datetime(2026, 3, 20, 17, 30),
    check_interval=60,  # 每分钟检查一次
    execute_func=your_function,
    **kwargs
)
```

### Q4: 如何处理数据库连接错误？

```python
from gs2026.utils.decorators_util import retry

@retry(max_attempts=3, delay=5.0, exceptions=(OperationalError,))
def query_database():
    # 数据库查询逻辑
    pass
```

### Q5: 如何自定义日志文件？

```python
from gs2026.utils.decorators_util import log_decorator

@log_decorator(log_level="INFO", log_args=True, log_file="custom.log")
def my_function():
    pass
```

---

## 更多帮助

- 查看 [架构设计文档](ARCHITECTURE.md)
- 查看 [装饰器指南](DECORATORS_GUIDE.md)
- 查看 [变更日志](CHANGELOG.md)
