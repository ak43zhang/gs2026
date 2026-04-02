# 数据库监控禁用问题排查报告

> 排查时间: 2026-03-31 10:07  
> 问题: 数据库监控显示"已禁用"

---

## 一、调用链分析

### 1.1 完整调用流程

```
Flask启动
    ↓
app.py 导入 DBProfiler
    ↓
data_service.py DataService.__init__()
    ├── 创建引擎
    ├── 读取 settings.yaml 配置
    ├── 判断 enabled = True
    ├── DBProfiler(enabled=True)  ← 第一次创建实例
    │       ├── _initialized = False
    │       ├── 读取配置
    │       ├── self.enabled = True  ✓
    │       ├── _initialized = True
    │       └── 返回实例
    └── profiler.attach_to_engine(engine)  ← 附加成功
    ↓
app.py 注册诊断路由
    ├── DBProfiler()  ← 第二次创建实例！
    │       ├── _initialized = True (已初始化过)
    │       ├── 直接返回已存在的单例
    │       └── 但单例的 enabled 可能为 False
    └── _db_profiler_instance = DBProfiler()
        ├── _initialized = False (被强制重置)
        ├── __init__() 重新初始化
        ├── 读取配置
        └── self.enabled = ?
```

### 1.2 问题定位

**问题1: 单例模式被破坏**
- `app.py` 中强制重置 `_initialized = False`
- 然后调用 `__init__()` 重新初始化
- 这破坏了单例模式，导致状态不一致

**问题2: 配置路径可能不同**
- `db_profiler.py` 中的 `_load_db_profiler_config()` 使用相对路径
- `Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'`
- 如果路径解析错误，配置读取失败，默认 enabled=False

**问题3: 初始化顺序问题**
- `data_service.py` 先创建实例并传入 `enabled=True`
- `app.py` 后又强制重新初始化
- 第二次初始化可能读取不到配置

---

## 二、根本原因

### 2.1 代码问题

**app.py 中的错误代码:**
```python
_db_profiler_instance = DBProfiler()
# 强制重新初始化，确保读取最新配置  ← 这是错误的！
_db_profiler_instance._initialized = False
_db_profiler_instance.__init__()
```

**问题:**
1. 强制重置 `_initialized` 破坏了单例模式
2. 直接调用 `__init__()` 不会重新走 `__new__()` 的单例判断
3. 第二次初始化时，配置读取可能失败

### 2.2 配置读取问题

**db_profiler.py 中的配置加载:**
```python
def _load_db_profiler_config():
    config_path = Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'
```

**路径解析:**
- db_profiler.py 位置: `src/gs2026/dashboard2/middleware/db_profiler.py`
- parent: `src/gs2026/dashboard2/middleware/`
- parent.parent: `src/gs2026/dashboard2/`
- parent.parent.parent: `src/gs2026/`
- parent.parent.parent.parent: `src/`
- 期望路径: `src/configs/settings.yaml` ❌
- 实际路径: `configs/settings.yaml` (项目根目录)

**结论: 配置路径错误！**

---

## 三、解决方案

### 方案A: 修复配置路径（推荐）

**修改 db_profiler.py:**
```python
def _load_db_profiler_config():
    """从 settings.yaml 加载数据库分析器配置"""
    try:
        # 尝试多种路径
        possible_paths = [
            # 从项目根目录
            Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml',
            # 从当前文件向上4层
            Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml',
            # 绝对路径（通过环境变量）
            Path(os.environ.get('PROJECT_ROOT', '')) / 'configs' / 'settings.yaml' if os.environ.get('PROJECT_ROOT') else None,
        ]
        
        for config_path in possible_paths:
            if config_path and config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    return config.get('db_profiler', {})
    except Exception as e:
        logger.warning(f"加载 db_profiler 配置失败: {e}")
    return {}
```

**修改 app.py:**
```python
# 删除强制重新初始化的代码
_db_profiler_instance = DBProfiler()  # 直接使用单例
```

### 方案B: 使用环境变量强制启用

**临时解决方案:**
```bash
set ENABLE_DB_PROFILER=1
```

然后在 app.py 和 data_service.py 中优先检查环境变量。

### 方案C: 重构单例模式

**修改 db_profiler.py:**
```python
class DBProfiler:
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls, **kwargs):
        """获取单例实例，支持更新配置"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance
    
    def __init__(self, enabled=None, slow_threshold_ms=None):
        # 如果已经初始化，更新配置
        if self._initialized:
            if enabled is not None:
                self.enabled = enabled
            return
        
        # 首次初始化...
```

---

## 四、推荐方案

### 推荐: 方案A + 删除 app.py 中的强制重置

**原因:**
1. 修复配置路径是根本解决方案
2. 删除强制重置代码，保持单例模式正确性
3. 不影响其他功能

**实施步骤:**
1. 修复 db_profiler.py 配置路径
2. 删除 app.py 中的 `_initialized = False` 和 `__init__()` 调用
3. 测试验证

---

## 五、验证方法

**1. 检查配置读取:**
```python
from gs2026.dashboard2.middleware.db_profiler import _load_db_profiler_config
print(_load_db_profiler_config())
```

**2. 检查实例状态:**
```python
from gs2026.dashboard2.middleware.db_profiler import DBProfiler
p = DBProfiler()
print(f"enabled: {p.enabled}")
print(f"_initialized: {p._initialized}")
```

**3. 检查诊断API:**
```
GET http://localhost:8080/diag/db
```

---

**文档位置**: `docs/db_profiler_issue_analysis.md`

**请确认方案后实施。**
