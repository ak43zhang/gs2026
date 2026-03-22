# 装饰器使用手册

## 概述

GS2026 提供了一系列实用的装饰器，用于简化开发、增强日志记录、处理重试逻辑等。

## 装饰器列表

| 装饰器 | 用途 | 位置 |
|--------|------|------|
| `@log_decorator()` | 自动记录函数调用日志 | `gs2026.utils.decorators` |
| `@retry()` | 自动重试失败的操作 | `gs2026.utils.decorators` |
| `@timing` | 记录函数执行时间 | `gs2026.utils.decorators` |
| `@deprecated()` | 标记弃用的函数 | `gs2026.utils.decorators` |
| `@singleton` | 单例模式 | `gs2026.utils.decorators` |

---

## 1. 日志装饰器 (@log_decorator)

### 功能

自动记录函数的调用、参数、返回值和异常信息。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `log_level` | str | `"INFO"` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `log_args` | bool | `True` | 是否记录参数 |
| `log_result` | bool | `False` | 是否记录返回值 |
| `log_exception` | bool | `True` | 是否记录异常 |

### 使用示例

#### 基本用法

```python
from gs2026.utils.decorators import log_decorator

@log_decorator()
def add(a, b):
    """加法函数"""
    return a + b

result = add(1, 2)
# 日志输出:
# [gs2026.utils.test] 调用 add | 参数: 1, 2
# [gs2026.utils.test] add 完成 | 耗时: 0.001s
```

#### 记录返回值

```python
@log_decorator(log_level="DEBUG", log_result=True)
def fetch_data(url):
    """获取数据"""
    return requests.get(url).json()

# 日志输出:
# [gs2026.utils.test] 调用 fetch_data | 参数: url=https://api.example.com
# [gs2026.utils.test] fetch_data 完成 | 耗时: 0.523s | 返回: {...}
```

#### 异常记录

```python
@log_decorator(log_exception=True)
def divide(a, b):
    """除法"""
    return a / b

try:
    divide(10, 0)
except ZeroDivisionError:
    pass
# 日志输出:
# [gs2026.utils.test] divide 异常 | 耗时: 0.001s | 错误: division by zero
# Traceback: ...
```

---

## 2. 重试装饰器 (@retry)

### 功能

当函数执行失败时自动重试，支持指数退避。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_attempts` | int | `3` | 最大重试次数 |
| `delay` | float | `1.0` | 初始延迟（秒） |
| `backoff` | float | `2.0` | 退避因子 |
| `exceptions` | tuple | `(Exception,)` | 捕获的异常类型 |
| `log_retries` | bool | `True` | 是否记录重试日志 |

### 使用示例

#### 基本用法

```python
from gs2026.utils.decorators import retry

@retry(max_attempts=3, delay=1.0)
def fetch_data(url):
    """获取数据，失败自动重试"""
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

# 如果失败，会自动重试3次，间隔1秒、2秒、4秒
```

#### 自定义异常类型

```python
@retry(
    max_attempts=5,
    delay=0.5,
    exceptions=(ConnectionError, TimeoutError)
)
def connect_database():
    """连接数据库"""
    return create_connection()

# 只捕获 ConnectionError 和 TimeoutError
```

#### 快速重试

```python
@retry(max_attempts=10, delay=0.1, backoff=1.5)
def check_status():
    """快速检查状态"""
    return get_service_status()
```

---

## 3. 计时装饰器 (@timing)

### 功能

记录函数的执行时间。

### 使用示例

```python
from gs2026.utils.decorators import timing

@timing
def process_large_data(data):
    """处理大量数据"""
    result = []
    for item in data:
        result.append(item * 2)
    return result

# 日志输出:
# process_large_data 执行耗时: 2.345秒
```

---

## 4. 弃用装饰器 (@deprecated)

### 功能

标记函数为已弃用，调用时发出警告。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `reason` | str | `""` | 弃用原因和替代方案 |

### 使用示例

```python
from gs2026.utils.decorators import deprecated

@deprecated("请使用 new_function 代替")
def old_function():
    """旧函数"""
    return "old"

# 调用时日志输出:
# old_function 已弃用: 请使用 new_function 代替
```

---

## 5. 单例装饰器 (@singleton)

### 功能

确保类只有一个实例。

### 使用示例

```python
from gs2026.utils.decorators import singleton

@singleton
class Database:
    """数据库连接"""
    def __init__(self):
        self.connection = create_connection()

# 无论创建多少次，都是同一个实例
db1 = Database()
db2 = Database()
assert db1 is db2  # True
```

---

## 6. 组合使用

多个装饰器可以组合使用：

```python
from gs2026.utils.decorators import log_decorator, retry, timing

@timing
@retry(max_attempts=3, delay=1.0)
@log_decorator(log_level="INFO", log_result=True)
def fetch_and_process(url):
    """获取并处理数据"""
    data = requests.get(url).json()
    return process_data(data)

# 执行顺序（从内到外）:
# 1. log_decorator: 记录调用和结果
# 2. retry: 失败时重试
# 3. timing: 记录总耗时
```

---

## 7. 日志文件位置

使用 `@log_decorator` 的函数会自动创建日志文件：

```
gs2026/logs/
├── gs2026_utils_test_add.log
├── gs2026_utils_test_fetch_data.log
└── ...
```

日志文件特点：
- 按模块和函数名命名
- 自动轮转（10MB）
- 保留30天
- 旧日志自动压缩

---

## 8. 测试

运行装饰器测试：

```bash
cd F:\pyworkspace\gs2026

# 运行所有测试
pytest tests/test_decorators.py -v

# 运行特定测试类
pytest tests/test_decorators.py::TestLogDecorator -v

# 运行特定测试方法
pytest tests/test_decorators.py::TestRetryDecorator::test_retry_success_first_attempt -v
```

---

## 9. 最佳实践

### 日志装饰器

```python
# ✅ 推荐：用于关键业务函数
@log_decorator(log_level="INFO", log_result=True)
def create_order(user_id, product_id):
    pass

# ❌ 不推荐：用于频繁调用的简单函数
@log_decorator()
def get_current_time():
    return datetime.now()
```

### 重试装饰器

```python
# ✅ 推荐：用于网络请求、数据库连接
@retry(max_attempts=3, delay=1.0)
def call_api():
    pass

# ❌ 不推荐：用于本地计算
@retry(max_attempts=3)
def calculate(x, y):
    return x + y
```

### 计时装饰器

```python
# ✅ 推荐：用于性能敏感的操作
@timing
def heavy_computation():
    pass
```

---

## 10. 故障排除

### 日志文件未创建

检查 `gs2026/config/settings.py` 中的 `log_dir` 配置：

```python
settings.log_dir  # 应该指向 gs2026/logs
```

### 重试不生效

确保捕获正确的异常类型：

```python
# ✅ 正确
@retry(exceptions=(ConnectionError, TimeoutError))
def fetch():
    pass

# ❌ 错误 - 捕获所有异常可能隐藏问题
@retry(exceptions=(Exception,))
def fetch():
    pass
```

---

## 参考

- 源码位置: `src/gs2026/utils/decorators.py`
- 测试位置: `tests/test_decorators.py`
- 基于 gs2025 `exe/tools/log_tool.py` 改写
