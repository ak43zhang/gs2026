# SQLAlchemy 程序退出时 ConnectionAbortedError / MySQL server has gone away 解决方案

## 问题现象

程序正常执行完毕后，退出时报错：

```
Exception during reset or similar
Traceback (most recent call last):
  File "pymysql/connections.py", line 813, in _write_bytes
    self._sock.sendall(data)
ConnectionAbortedError: [WinError 10053] 你的主机中的软件中止了一个已建立的连接。

pymysql.err.OperationalError: (2006, "MySQL server has gone away")
```

## 根因

程序运行过程中，SQLAlchemy 连接池中的连接因 MySQL 服务端 idle timeout（默认8小时）被断开。程序退出时，Python 垃圾回收器尝试归还连接池中的连接，触发 rollback 操作，但连接已断开，导致异常。

## 解决方案

### 1. 创建引擎时添加 `pool_pre_ping=True`

```python
# 修复前
engine = create_engine(url)

# 修复后
engine = create_engine(url, pool_pre_ping=True)
```

**作用**：每次从连接池获取连接时，先发送一个轻量级 ping 检测连接是否存活。如果连接已断开，自动丢弃并创建新连接。

### 2. 程序退出前调用 `engine.dispose()`

```python
# 在 main_loop 退出时
logger.info("进程已停止")
engine.dispose()  # 优雅关闭连接池，避免退出时 ConnectionAbortedError
```

**作用**：主动关闭连接池中所有连接，不再依赖垃圾回收器清理。

## 适用场景

- 长时间运行的后台进程（如监控、分析、采集程序）
- 任何使用 SQLAlchemy + PyMySQL 连接 MySQL 的 Python 程序
- 程序运行时间可能超过 MySQL `wait_timeout`（默认28800秒=8小时）的场景

## 关键参数

| 参数 | 作用 | 推荐值 |
|------|------|--------|
| `pool_pre_ping=True` | 使用前检测连接存活 | 始终开启 |
| `pool_recycle=3600` | 连接池自动回收时间(秒) | 3600（1小时） |
| `engine.dispose()` | 关闭所有连接 | 程序退出前调用 |

## 完整示例

```python
from sqlalchemy import create_engine

# 创建引擎（推荐配置）
engine = create_engine(
    url, 
    pool_pre_ping=True,      # 检测失效连接
    pool_recycle=3600         # 1小时自动回收
)

# ... 程序逻辑 ...

# 退出前清理
engine.dispose()
```

## 相关错误

以下错误均属同一类问题：
- `ConnectionAbortedError: [WinError 10053]`
- `pymysql.err.OperationalError: (2006, "MySQL server has gone away")`
- `sqlalchemy.exc.PendingRollbackError: Can't reconnect until invalid transaction is rolled back`
- `BrokenPipeError: [Errno 32] Broken pipe`

## 修复记录

- 提交 `1901d31`: anomaly_analyzer.py + anomaly_correlator.py
- 提交 `f8d1102`: baostock_collection.py + zt_collection.py + bk_gn_collection.py + wencai_collection.py
