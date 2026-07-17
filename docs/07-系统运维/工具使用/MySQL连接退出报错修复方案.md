# MySQL连接退出报错修复方案 - Engine集中管理

## 问题描述

程序正常结束后报错：

```
Exception during reset or similar
pymysql.err.OperationalError: (2006, "MySQL server has gone away 
(ConnectionAbortedError(10053, '你的主机中的软件中止了一个已建立的连接。'))")
```

## 根因分析

1. 程序退出时，Python GC 销毁 SQLAlchemy Engine 对象
2. 连接池中残留的连接在被回收时，Pool 尝试对每个连接执行 `ROLLBACK`
3. 此时连接已被 MySQL 服务器超时断开 / 被系统网络层关闭
4. 于是触发 `MySQL server has gone away` 异常

## 影响范围

- **不影响业务**：主逻辑已经执行完毕
- **不影响数据**：所有业务操作都已经 commit
- **日志难看**：每次正常退出都有 traceback

## 涉及文件

项目中共 **56个文件** 使用模块级 `engine = create_engine(...)`，退出时都可能触发。

## 解决方案

### 方案：集中式 `get_engine()` 函数

在 `config_util.py` 中新增 `get_engine()` 函数：

```python
import atexit
from sqlalchemy import create_engine as _sa_create_engine

_shared_engine = None

def get_engine(pool_size=5, max_overflow=10, **kwargs):
    """获取全局共享 Engine（单例 + atexit 自动清理）"""
    global _shared_engine
    if _shared_engine is None:
        url = get_config("common.url")
        _shared_engine = _sa_create_engine(
            url,
            pool_recycle=3600,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            **kwargs
        )
        atexit.register(_shared_engine.dispose)
    return _shared_engine
```

### 各文件改动

**原来（3行）**：
```python
from sqlalchemy import create_engine
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
```

**改为（1行）**：
```python
engine = config_util.get_engine()
```

### 优势

| 方面 | 逐文件加 atexit | 集中式 get_engine() |
|------|----------------|---------------------|
| 核心改动 | 无新函数 | config_util.py 加1个函数 |
| 每个文件 | +2行 | 删2行 + 改1行（净减少） |
| 后续新文件 | 每次都要记得加 atexit | 调 get_engine() 不会遗漏 |
| 连接管理 | 各文件独立 engine | 同进程共享（减少连接数） |
| 参数统一 | 各文件各自配置 | 集中管控 |

### 特殊情况

| 情况 | 处理方式 |
|------|----------|
| 需要自定义 pool_size | `engine = config_util.get_engine(pool_size=20)` |
| `_get_engine()` 函数模式 | 内部改为 `return config_util.get_engine()` |
| Flask Web 应用 | 不改（长驻进程不需要） |

## 实施记录

- 回退点 Commit: `2e6d056`
- 实施日期: 2025-07-01
- 修改文件数: 56个
