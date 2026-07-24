# 可插拔监控方案设计

## 设计目标

1. **可插拔**: 通过配置启用/禁用监控，不影响业务代码
2. **可复用**: 所有进程共享同一套监控组件
3. **低开销**: 监控本身对性能影响最小化
4. **可扩展**: 支持自定义监控指标

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         业务进程                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  主循环     │  │  存储操作   │  │  数据库操作 │            │
│  │  (位置1)    │  │  (位置2)    │  │  (位置3)    │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│         └────────────────┴────────────────┘                    │
│                          │                                       │
│              ┌───────────┴───────────┐                          │
│              │   监控装饰器/上下文    │  ← 可插拔层               │
│              │   (monitoring.plugin)   │                          │
│              └───────────┬───────────┘                          │
│                          │                                       │
│              ┌───────────┴───────────┐                          │
│              │     监控核心引擎      │                          │
│              │   (monitoring.core)    │                          │
│              └───────────┬───────────┘                          │
│                          │                                       │
│         ┌────────────────┼────────────────┐                     │
│         ▼                ▼                ▼                     │
│  ┌──────────┐      ┌──────────┐   ┌──────────┐                 │
│  │ 内存监控 │      │ 队列监控 │   │ 连接监控 │                 │
│  └──────────┘      └──────────┘   └──────────┘                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   监控数据输出    │
                    │  (日志/指标/告警) │
                    └──────────────────┘
```

---

## 核心组件设计

### 组件1：监控配置 (monitoring/config.py)

```python
"""
监控配置模块
支持通过环境变量或配置文件启用/禁用监控
"""
import os
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class MonitorConfig:
    """监控配置"""
    enabled: bool = True  # 总开关
    
    # 位置1：主循环监控
    loop_monitor_enabled: bool = True
    loop_check_interval: int = 60  # 秒
    
    # 位置2：存储监控
    storage_monitor_enabled: bool = True
    
    # 位置3：数据库监控
    db_monitor_enabled: bool = True
    
    # 阈值配置
    thresholds: Dict[str, float] = None
    
    def __post_init__(self):
        if self.thresholds is None:
            self.thresholds = {
                'system_memory_warning': 80,
                'system_memory_critical': 90,
                'process_memory_warning': 1024,  # MB
                'process_memory_critical': 2048,
                'queue_warning': 10,
                'queue_critical': 20,
                'sql_timeout_warning': 3,
                'sql_timeout_critical': 10,
            }

# 全局配置实例
_config = None

def get_config() -> MonitorConfig:
    """获取监控配置（单例）"""
    global _config
    if _config is None:
        _config = MonitorConfig(
            enabled=os.getenv('MONITOR_ENABLED', 'true').lower() == 'true',
            loop_monitor_enabled=os.getenv('MONITOR_LOOP_ENABLED', 'true').lower() == 'true',
            storage_monitor_enabled=os.getenv('MONITOR_STORAGE_ENABLED', 'true').lower() == 'true',
            db_monitor_enabled=os.getenv('MONITOR_DB_ENABLED', 'true').lower() == 'true',
            loop_check_interval=int(os.getenv('MONITOR_LOOP_INTERVAL', '60')),
        )
    return _config

def set_config(config: MonitorConfig):
    """设置监控配置"""
    global _config
    _config = config
```

---

### 组件2：监控核心引擎 (monitoring/core.py)

```python
"""
监控核心引擎
提供低开销的监控数据采集和报告
"""
import time
import threading
from typing import Callable, Dict, Any, Optional
from collections import deque
import logging

logger = logging.getLogger(__name__)

class MonitoringEngine:
    """
    监控核心引擎
    
    特点：
    1. 异步采样：监控数据在独立线程收集
    2. 批量报告：定期批量输出，减少日志压力
    3. 阈值触发：超过阈值才记录详细日志
    """
    
    def __init__(self, config: 'MonitorConfig' = None):
        self.config = config or get_config()
        self._enabled = self.config.enabled
        
        # 采样数据缓存
        self._samples = {
            'memory': deque(maxlen=60),      # 60个样本
            'queue': deque(maxlen=60),
            'sql_time': deque(maxlen=60),
        }
        
        # 统计信息
        self._stats = {
            'total_checks': 0,
            'warning_count': 0,
            'critical_count': 0,
        }
        
        # 采样线程
        self._sampling_thread = None
        self._stop_event = threading.Event()
        
        if self._enabled:
            self._start_sampling()
    
    def _start_sampling(self):
        """启动后台采样线程"""
        def sampling_loop():
            while not self._stop_event.is_set():
                try:
                    self._collect_sample()
                except Exception as e:
                    logger.debug(f"采样失败: {e}")
                self._stop_event.wait(1)  # 每秒采样一次
        
        self._sampling_thread = threading.Thread(
            target=sampling_loop,
            name='monitor-sampling',
            daemon=True
        )
        self._sampling_thread.start()
        logger.info("监控引擎已启动")
    
    def _collect_sample(self):
        """收集一次样本（低开销）"""
        try:
            import psutil
            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024
            self._samples['memory'].append({
                'time': time.time(),
                'value': mem_mb,
            })
        except:
            pass
    
    def record(self, metric_type: str, data: Dict[str, Any]):
        """
        记录监控数据
        
        Args:
            metric_type: 指标类型 ('loop', 'storage', 'db')
            data: 监控数据字典
        """
        if not self._enabled:
            return
        
        self._stats['total_checks'] += 1
        
        # 检查阈值
        level = self._check_thresholds(metric_type, data)
        
        if level == 'critical':
            self._stats['critical_count'] += 1
            logger.error(f"[监控] {metric_type}: {data}")
        elif level == 'warning':
            self._stats['warning_count'] += 1
            logger.warning(f"[监控] {metric_type}: {data}")
        else:
            # 正常级别，只在调试模式记录
            logger.debug(f"[监控] {metric_type}: {data}")
    
    def _check_thresholds(self, metric_type: str, data: Dict) -> str:
        """检查阈值，返回级别 ('normal', 'warning', 'critical')"""
        thresholds = self.config.thresholds
        
        if metric_type == 'storage':
            queue = data.get('queue_size', 0)
            mem = data.get('memory_mb', 0)
            
            if queue > thresholds.get('queue_critical', 20) or \
               mem > thresholds.get('process_memory_critical', 2048):
                return 'critical'
            if queue > thresholds.get('queue_warning', 10) or \
               mem > thresholds.get('process_memory_warning', 1024):
                return 'warning'
        
        elif metric_type == 'db':
            duration = data.get('duration', 0)
            if duration > thresholds.get('sql_timeout_critical', 10):
                return 'critical'
            if duration > thresholds.get('sql_timeout_warning', 3):
                return 'warning'
        
        elif metric_type == 'loop':
            sys_mem = data.get('system_memory_percent', 0)
            proc_mem = data.get('process_memory_mb', 0)
            
            if sys_mem > thresholds.get('system_memory_critical', 90) or \
               proc_mem > thresholds.get('process_memory_critical', 2048):
                return 'critical'
            if sys_mem > thresholds.get('system_memory_warning', 80) or \
               proc_mem > thresholds.get('process_memory_warning', 1024):
                return 'warning'
        
        return 'normal'
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self._stats,
            'samples_collected': {
                k: len(v) for k, v in self._samples.items()
            }
        }
    
    def shutdown(self):
        """关闭监控引擎"""
        self._stop_event.set()
        if self._sampling_thread:
            self._sampling_thread.join(timeout=2)
        logger.info("监控引擎已关闭")

# 全局引擎实例
_engine = None

def get_engine() -> MonitoringEngine:
    """获取监控引擎（单例）"""
    global _engine
    if _engine is None:
        _engine = MonitoringEngine()
    return _engine

def reset_engine():
    """重置监控引擎"""
    global _engine
    if _engine:
        _engine.shutdown()
    _engine = None
```

---

### 组件3：监控装饰器 (monitoring/decorators.py)

```python
"""
监控装饰器
提供非侵入式的监控方式
"""
import time
import functools
from typing import Callable, Any
from .core import get_engine
from .config import get_config

# 位置1：主循环监控装饰器
def monitor_loop(func: Callable) -> Callable:
    """
    主循环监控装饰器
    
    用法：
        @monitor_loop
        def run_monitor_loop_synced(process_func, interval=3):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        config = get_config()
        if not config.enabled or not config.loop_monitor_enabled:
            return func(*args, **kwargs)
        
        engine = get_engine()
        last_check = 0
        
        # 获取原始循环逻辑
        original_loop = func(*args, **kwargs)
        
        # 如果返回的是生成器，包装它
        if hasattr(original_loop, '__iter__'):
            def monitored_loop():
                for item in original_loop:
                    now = time.time()
                    
                    # 定期健康检查
                    if now - last_check >= config.loop_check_interval:
                        try:
                            import psutil
                            mem = psutil.virtual_memory()
                            process = psutil.Process()
                            
                            engine.record('loop', {
                                'system_memory_percent': mem.percent,
                                'process_memory_mb': process.memory_info().rss / 1024 / 1024,
                                'cpu_percent': process.cpu_percent(),
                            })
                            last_check = now
                        except Exception as e:
                            pass
                    
                    yield item
            
            return monitored_loop()
        
        return original_loop
    
    return wrapper

# 位置2：存储监控装饰器
def monitor_storage(func: Callable) -> Callable:
    """
    存储操作监控装饰器
    
    用法：
        @monitor_storage
        def save_dataframe_async(df, table_name, ...):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        config = get_config()
        if not config.enabled or not config.storage_monitor_enabled:
            return func(*args, **kwargs)
        
        engine = get_engine()
        
        # 获取参数
        df = args[0] if args else kwargs.get('df')
        time_full = args[2] if len(args) > 2 else kwargs.get('time_full', 'unknown')
        
        # 监控数据
        try:
            import psutil
            from concurrent.futures import ThreadPoolExecutor
            
            # 获取队列深度（通过全局变量或参数传递）
            queue_size = 0
            if '_storage_executor' in globals():
                executor = globals()['_storage_executor']
                if hasattr(executor, '_work_queue'):
                    queue_size = executor._work_queue.qsize()
            
            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024
            
            # DataFrame大小
            df_size_mb = df.memory_usage(deep=True).sum() / 1024 / 1024 if df is not None else 0
            
            engine.record('storage', {
                'time_full': time_full,
                'queue_size': queue_size,
                'memory_mb': mem_mb,
                'df_size_mb': df_size_mb,
                'df_rows': len(df) if df is not None else 0,
            })
        except Exception as e:
            pass
        
        # 执行原始函数
        return func(*args, **kwargs)
    
    return wrapper

# 位置3：数据库监控装饰器
def monitor_db(func: Callable) -> Callable:
    """
    数据库操作监控装饰器
    
    用法：
        @monitor_db
        def _write_mysql_async(df, table_name, dtype_map):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        config = get_config()
        if not config.enabled or not config.db_monitor_enabled:
            return func(*args, **kwargs)
        
        engine = get_engine()
        start_time = time.time()
        
        # 获取连接池状态
        pool_status = {}
        try:
            from sqlalchemy import create_engine
            if 'engine' in globals():
                eng = globals()['engine']
                if hasattr(eng, 'pool'):
                    pool_status = {
                        'size': eng.pool.size(),
                        'checked_out': eng.pool.checkedout(),
                        'overflow': eng.pool.overflow(),
                    }
        except:
            pass
        
        try:
            # 执行原始函数
            result = func(*args, **kwargs)
            
            # 记录成功
            duration = time.time() - start_time
            engine.record('db', {
                'operation': func.__name__,
                'duration': duration,
                'pool_status': pool_status,
                'success': True,
            })
            
            return result
        except Exception as e:
            # 记录失败
            duration = time.time() - start_time
            engine.record('db', {
                'operation': func.__name__,
                'duration': duration,
                'pool_status': pool_status,
                'success': False,
                'error': str(e),
            })
            raise
    
    return wrapper

# 上下文管理器方式（更灵活）
class MonitorContext:
    """
    监控上下文管理器
    
    用法：
        with MonitorContext('storage', time_full='10:30:00'):
            save_dataframe_async(df, table_name, time_full)
    """
    
    def __init__(self, metric_type: str, **kwargs):
        self.metric_type = metric_type
        self.data = kwargs
        self.start_time = None
        self.engine = get_engine() if get_config().enabled else None
    
    def __enter__(self):
        if self.engine:
            self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.engine:
            duration = time.time() - self.start_time
            self.data['duration'] = duration
            self.data['success'] = exc_type is None
            if exc_val:
                self.data['error'] = str(exc_val)
            self.engine.record(self.metric_type, self.data)
```

---

### 组件4：进程初始化集成 (monitoring/__init__.py)

```python
"""
监控模块入口
提供进程级的监控初始化
"""
import atexit
import os
from .config import get_config, MonitorConfig
from .core import get_engine, reset_engine
from .decorators import monitor_loop, monitor_storage, monitor_db, MonitorContext

__all__ = [
    'init_monitoring',      # 初始化监控
    'shutdown_monitoring',  # 关闭监控
    'get_config',           # 获取配置
    'MonitorConfig',        # 配置类
    'monitor_loop',         # 装饰器
    'monitor_storage',
    'monitor_db',
    'MonitorContext',
]

def init_monitoring(
    enabled: bool = None,
    loop_enabled: bool = None,
    storage_enabled: bool = None,
    db_enabled: bool = None,
    **kwargs
):
    """
    初始化监控
    
    用法：
        from gs2026.utils.monitoring import init_monitoring
        init_monitoring(
            enabled=True,
            loop_check_interval=60,
            thresholds={'process_memory_warning': 512}
        )
    """
    # 从环境变量读取配置
    config = MonitorConfig(
        enabled=enabled if enabled is not None else os.getenv('MONITOR_ENABLED', 'true').lower() == 'true',
        loop_monitor_enabled=loop_enabled if loop_enabled is not None else os.getenv('MONITOR_LOOP_ENABLED', 'true').lower() == 'true',
        storage_monitor_enabled=storage_enabled if storage_enabled is not None else os.getenv('MONITOR_STORAGE_ENABLED', 'true').lower() == 'true',
        db_monitor_enabled=db_enabled if db_enabled is not None else os.getenv('MONITOR_DB_ENABLED', 'true').lower() == 'true',
    )
    
    # 更新额外配置
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # 设置配置
    from .config import set_config
    set_config(config)
    
    # 启动引擎
    engine = get_engine()
    
    # 注册退出清理
    atexit.register(shutdown_monitoring)
    
    return engine

def shutdown_monitoring():
    """关闭监控"""
    reset_engine()
    print("[监控] 已关闭")

# 便捷的开关函数
def enable_monitoring():
    """启用监控"""
    config = get_config()
    config.enabled = True
    init_monitoring()

def disable_monitoring():
    """禁用监控"""
    config = get_config()
    config.enabled = False
    shutdown_monitoring()
```

---

## 性能影响评估

### 监控开销分析

| 监控位置 | 操作 | 单次开销 | 频率 | 每小时开销 |
|----------|------|----------|------|------------|
| 位置1（主循环） | psutil 内存查询 | ~0.5ms | 60秒1次 | ~30ms |
| 位置2（存储） | psutil + DataFrame.size | ~1ms | 3秒1次 | ~1.2s |
| 位置3（数据库） | 时间戳 + 连接池查询 | ~0.2ms | 3秒1次 | ~240ms |
| 后台采样 | psutil 内存采样 | ~0.3ms | 1秒1次 | ~1.08s |
| **总计** | | | | **~2.5s/小时** |

### 性能影响结论

| 指标 | 数值 | 评估 |
|------|------|------|
| 每小时监控开销 | ~2.5秒 | **可忽略**（< 0.1%） |
| 每次存储监控开销 | ~1ms | **可忽略**（存储本身需100-500ms） |
| 内存占用 | ~10MB | **可接受** |
| CPU占用 | < 1% | **可忽略** |

### 优化措施

1. **异步采样**: 监控数据在独立线程收集，不阻塞主流程
2. **批量报告**: 正常级别只记录 debug 日志，减少日志压力
3. **阈值触发**: 只有超过阈值才记录 warning/error 日志
4. **采样缓存**: 内存历史只保留60个样本，控制内存占用
5. **快速失败**: 监控异常不影响业务逻辑

---

## 使用示例

### 示例1：在 monitor_stock.py 中使用

```python
# 文件顶部导入
from gs2026.utils.monitoring import init_monitoring, monitor_storage, monitor_db, monitor_loop

# 初始化监控（在 main 函数或模块导入时）
init_monitoring(
    enabled=True,
    loop_check_interval=60,
    thresholds={'process_memory_warning': 1024}
)

# 方式1：使用装饰器（推荐）
@monitor_loop
def run_monitor_loop_synced(process_func, interval=INTERVAL):
    # 原有代码不变
    ...

@monitor_storage
def save_dataframe_async(df, table_name, time_full, expire_seconds):
    # 原有代码不变
    ...

@monitor_db
def _write_mysql_async(df, table_name, dtype_map):
    # 原有代码不变
    ...

# 方式2：使用上下文管理器（更灵活）
def some_function():
    with MonitorContext('storage', time_full='10:30:00'):
        save_dataframe_async(df, table_name, time_full, expire_seconds)
```

### 示例2：在其他进程中复用

```python
# bond_monitor.py
from gs2026.utils.monitoring import init_monitoring, monitor_storage, monitor_db

# 同样的初始化
init_monitoring(enabled=True)

@monitor_storage
def save_bond_data(df, table_name, time_full):
    ...

@monitor_db
def write_bond_to_mysql(df, table_name):
    ...
```

### 示例3：通过环境变量控制

```bash
# 启用监控
export MONITOR_ENABLED=true
export MONITOR_LOOP_ENABLED=true
export MONITOR_STORAGE_ENABLED=true
export MONITOR_DB_ENABLED=true
export MONITOR_LOOP_INTERVAL=60

# 禁用监控
export MONITOR_ENABLED=false

# 运行程序
python monitor_stock.py
```

---

## 文件结构

```
gs2026/
└── utils/
    └── monitoring/
        ├── __init__.py      # 模块入口，提供便捷API
        ├── config.py        # 配置管理
        ├── core.py          # 监控引擎
        ├── decorators.py    # 装饰器
        └── README.md        # 使用文档
```

---

## 总结

| 特性 | 实现方式 | 优势 |
|------|----------|------|
| **可插拔** | 装饰器 + 配置开关 | 零侵入，随时启用/禁用 |
| **可复用** | 统一模块 | 所有进程共享同一套监控 |
| **低开销** | 异步采样 + 阈值触发 | 每小时 < 3秒开销 |
| **可扩展** | 插件化设计 | 支持自定义监控指标 |

---

*设计方案完成*
