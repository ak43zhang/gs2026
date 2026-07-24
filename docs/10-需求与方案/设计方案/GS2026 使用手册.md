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

## Dashboard Web 界面

GS2026 提供 Web 界面管理数据采集和 AI 分析服务。

### 启动 Dashboard

```bash
# 启动 Flask 应用
python -m gs2026.dashboard.app

# 或指定端口
python -m gs2026.dashboard.app --port 5000
```

访问 http://localhost:5000

### 功能模块

#### 1. 监控面板 (/monitor)

实时显示市场数据：
- **市场概览** - 股票指数、债券指数实时行情
- **板块监控** - 行业板块涨跌幅排行
- **攻击排行** - 股票/债券实时攻击排行（带变化标记）
- **Combine 信号** - 股债联动信号（30秒内红色高亮）
- **详情图表** - 点击信号查看债券/股票分时图

#### 2. 数据采集 & 分析 (/control)

**数据采集 Tab：**
- 五个独立监控服务：stock, bond, industry, dp_signal, gp_zq_signal
- 全局启动/停止按钮
- 实时状态显示（运行中/已停止 + PID）

**数据分析 Tab：**
- 五个 AI 分析服务：
  | 服务 | 参数 | 说明 |
  |------|------|------|
  | 事件驱动分析 | 日期列表 | 领域消息深度分析 |
  | 财联社新闻分析 | 轮询间隔(秒)、年份 | 财联社新闻 AI 分析 |
  | 综合新闻分析 | 轮询间隔(秒)、年份 | 综合财经新闻分析 |
  | 涨停板分析 | 日期列表 | 涨停股票分析 |
  | 公告分析 | 轮询间隔(秒) | 上市公司公告分析 |
- 参数表单动态生成
- 实时日志输出

---

## 问财 Cookie 配置

解决同花顺问财登录弹窗问题。

### 首次配置

```bash
# 运行 Cookie 配置工具
python tests/test_wencai_cookie_v2.py save
```

1. 自动打开浏览器访问问财
2. 手动登录账号
3. 按回车保存 Cookie
4. Cookie 保存到 `configs/wencai_cookies.json`

### 使用 Cookie

修改后的采集模块会自动加载 Cookie：
- `wencai_collection.py` - 问财基础/热度数据采集
- `zt_collection.py` - 涨停/炸板数据采集
- `monitor_stock_other_indicators.py` - pywencai 查询

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

### Q6: 问财采集弹出登录窗口怎么办？

```bash
# 1. 运行 Cookie 配置工具
python tests/test_wencai_cookie_v2.py save

# 2. 按提示登录问财账号
# 3. Cookie 自动保存到 configs/wencai_cookies.json
# 4. 后续采集自动使用 Cookie，不再弹窗
```

### Q7: Dashboard 启动后如何访问？

```bash
# 启动 Dashboard
python -m gs2026.dashboard.app

# 访问 http://localhost:5000
# - /monitor - 监控面板
# - /control - 数据采集 & 分析控制面板
```

### Q8: 财联社分析启动后停止怎么办？

**临时解决方案：**
```bash
# 手动运行（正常）
python temp/run_news_cls.py
```

**问题原因：**
- 通过 `subprocess.Popen` 启动后进程被杀死
- 手动运行正常，可能是进程信号/控制台脱离问题
- 正在排查中

### Q9: 如何配置 Dashboard 的五个监控服务？

在 `control.html` 页面：
1. 切换到"数据采集" Tab
2. 点击服务卡片上的"启动"按钮
3. 查看状态指示灯（绿色=运行中）
4. 使用"启动全部"/"停止全部"批量控制

### Q10: 如何查看分析服务的运行日志？

```bash
# 实时查看财联社分析日志
tail -f logs/analysis/news_cls.log

# 查看所有分析服务日志
ls logs/analysis/
```

---

## 更多帮助

- 查看 [架构设计文档](ARCHITECTURE.md)
- 查看 [装饰器指南](DECORATORS_GUIDE.md)
- 查看 [变更日志](CHANGELOG.md)
