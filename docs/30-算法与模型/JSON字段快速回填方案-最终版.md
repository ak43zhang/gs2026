# JSON字段快速回填方案 - 复用现有架构设计（最终版）

## 一、当前方案（最终版）

### 1.1 核心设计原则

**"一次修改到处调用"** - 新增一个JSON字段，只需要修改**1个文件**（`monitor_bond.py`）。

### 1.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    monitor_bond.py（唯一修改）                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 全局状态变量 │  │ 计算函数    │  │ JSON_FIELD_REGISTRY │  │
│  │ _mkt_shape_ │  │ compute_    │  │ 字段注册表          │  │
│  │ history     │  │ mkt_shape() │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ compute_mkt_trend_indicators() - 实时计算调用            ││
│  │ get_json_field_registry() - 供外部读取注册表             ││
│  │ compute_json_field() - 通用计算接口                      ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────────┐
│ 实时计算       │    │ compute_engine│    │ backfill_json_    │
│ （每tick）     │    │ .py（回填引擎） │    │ fields.py（回填脚本）│
│               │    │               │    │                   │
│ 自动调用       │    │ 自动读取注册表 │    │ 自动读取注册表     │
│ 计算函数       │    │ 生成回填方法  │    │ 识别可回填字段     │
└───────────────┘    └───────────────┘    └───────────────────┘
```

### 1.3 文件职责

| 文件 | 职责 | 修改频率 |
|------|------|---------|
| `monitor_bond.py` | **唯一需要修改的文件**：状态变量、计算函数、注册表 | 新增字段时 |
| `compute_engine.py` | **一次性配置**：自动读取注册表，通用回填接口 | 仅首次 |
| `backfill_json_fields.py` | **一次性配置**：自动读取注册表，字段级UPDATE | 仅首次 |

### 1.4 关键机制

#### 机制1：字段注册表（JSON_FIELD_REGISTRY）

```python
# monitor_bond.py
JSON_FIELD_REGISTRY = {
    'mkt_shape': {
        'depends': ['mkt_vs_open_pct'],           # 依赖字段
        'computer': 'compute_mkt_shape',          # 计算函数名
        'needs_history': True,                    # 是否需要历史
        'state_vars': ['_mkt_shape_history'],     # 需要的全局状态
    },
    'mkt_shape_detail': {
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_shape_detail',
        'needs_history': True,
        'state_vars': ['_mkt_shape_history'],
    },
}

def get_json_field_registry():
    """供外部模块读取注册表"""
    return JSON_FIELD_REGISTRY
```

#### 机制2：通用计算接口（compute_json_field）

```python
def compute_json_field(field_name: str, dependencies: dict, history: list = None):
    """
    通用JSON字段计算接口
    
    供 compute_engine.py 统一调用，无需为每个字段写单独方法
    """
    registry = get_json_field_registry()
    config = registry[field_name]
    
    # 动态获取计算函数
    computer = globals()[config['computer']]
    
    # 调用计算
    if config.get('needs_history'):
        return computer(dependencies, history)
    return computer(dependencies)
```

#### 机制3：compute_engine自动适配

```python
# compute_engine.py（一次性配置）
class ComputeEngine:
    def __init__(self):
        # 自动导入注册表
        from monitor_bond import get_json_field_registry
        self.json_registry = get_json_field_registry()
        
        # 自动初始化注册表中声明的状态变量
        for field_config in self.json_registry.values():
            for state_var in field_config.get('state_vars', []):
                attr_name = state_var.lstrip('_')  # _mkt_shape_history → mkt_shape_history
                setattr(self, attr_name, [])
    
    def _compute_json_field(self, field_name: str, dependencies: dict):
        """通用回填计算（自动适配所有注册字段）"""
        from monitor_bond import compute_json_field
        
        # 获取历史数据
        history = []
        if self.json_registry[field_name].get('needs_history'):
            state_attr = self.json_registry[field_name]['state_vars'][0].lstrip('_')
            history = getattr(self, state_attr, [])
        
        # 调用统一计算接口
        return compute_json_field(field_name, dependencies, history)
```

#### 机制4：backfill_json_fields自动识别

```python
# backfill_json_fields.py（一次性配置）
from monitor_bond import get_json_field_registry

# 自动获取所有可回填字段
JSON_FIELDS = get_json_field_registry()

# 使用方式
# python backfill_json_fields.py --fields mkt_shape
# 自动识别 mkt_shape 在注册表中，使用对应的配置
```

---

## 二、新增字段完整流程

### 2.1 操作步骤（只需修改monitor_bond.py）

以新增 `mkt_trend_strength` 为例：

#### Step 1: 新增全局状态变量

```python
# 在文件顶部（其他全局变量附近）
_mkt_trend_strength_date = None
_mkt_trend_strength_cache = []
```

#### Step 2: 新增计算函数

```python
def compute_mkt_trend_strength(dependencies: dict, history: list) -> float:
    """
    计算大盘趋势强度（实时+回填共用）
    
    Args:
        dependencies: {'mkt_vs_open_pct': float, 'mkt_weighted_slope_10m': float}
        history: 历史数据（如果需要）
    
    Returns:
        趋势强度值（0-100）
    """
    vs_open = dependencies.get('mkt_vs_open_pct', 0)
    slope = dependencies.get('mkt_weighted_slope_10m', 0)
    
    # 计算逻辑...
    strength = min(100, max(0, abs(vs_open) + abs(slope) * 1000))
    
    return round(strength, 2)
```

#### Step 3: 在实时计算中调用

```python
def compute_mkt_trend_indicators(df_now, time_full, current_date):
    # ... 原有计算 ...
    
    # 更新状态
    global _mkt_trend_strength_date, _mkt_trend_strength_cache
    if _mkt_trend_strength_date != current_date:
        _mkt_trend_strength_cache = []
        _mkt_trend_strength_date = current_date
    
    # 计算
    deps = {
        'mkt_vs_open_pct': mkt_vs_open_pct,
        'mkt_weighted_slope_10m': mkt_weighted_slope_10m,
    }
    _mkt_trend_strength_cache.append(deps)
    
    mkt_trend_strength = compute_mkt_trend_strength(
        deps, 
        _mkt_trend_strength_cache[:-1]
    )
    
    return {
        # ... 原有字段 ...
        'mkt_trend_strength': mkt_trend_strength,
    }
```

#### Step 4: 在注册表中添加条目（关键！）

```python
JSON_FIELD_REGISTRY = {
    # ... 已有字段 ...
    
    'mkt_trend_strength': {
        'depends': ['mkt_vs_open_pct', 'mkt_weighted_slope_10m'],
        'computer': 'compute_mkt_trend_strength',
        'needs_history': True,
        'state_vars': ['_mkt_trend_strength_cache'],
    },
}
```

### 2.2 验证步骤

```bash
# 1. 实时计算测试
python -c "from monitor_bond import compute_mkt_trend_strength; print(compute_mkt_trend_strength({'mkt_vs_open_pct': 1.5}, []))"

# 2. 回填测试
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_trend_strength

# 3. 验证数据库
mysql -e "SELECT ext_indicators->>'$.mkt_trend_strength' FROM monitor_zq_sssj_20260723 LIMIT 5"
```

---

## 三、字段逻辑更新流程

### 3.1 更新计算逻辑

如果 `compute_mkt_shape` 的判定条件需要调整：

```python
# 只需修改 monitor_bond.py 中的计算函数
def compute_mkt_shape(dependencies: dict, history: list) -> str:
    # 修改判定逻辑
    if total_range < 0.3:  # 原来是 0.5
        return '横盘'
    # ... 其他修改 ...
```

**影响**：
- 实时计算：立即生效
- 回填：重新运行 `backfill_json_fields.py` 即可

### 3.2 更新依赖字段

如果 `mkt_shape` 需要增加依赖：

```python
# 修改注册表中的 depends
JSON_FIELD_REGISTRY['mkt_shape'] = {
    'depends': ['mkt_vs_open_pct', 'mkt_vwap_bias'],  # 增加依赖
    'computer': 'compute_mkt_shape',
    'needs_history': True,
    'state_vars': ['_mkt_shape_history'],
}

# 修改计算函数签名
def compute_mkt_shape(dependencies: dict, history: list) -> str:
    vs_open = dependencies.get('mkt_vs_open_pct')
    vwap_bias = dependencies.get('mkt_vwap_bias')  # 使用新依赖
    # ...
```

---

## 四、使用方式

### 4.1 实时计算

自动进行，无需额外操作。

### 4.2 历史回填

```bash
# 默认覆盖（无条件覆盖指定字段）
python scripts/backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail

# 跳过已有（只填充缺失key的行）
python scripts/backfill_json_fields.py --fields mkt_shape --skip-existing

# 单天回填
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_trend_strength

# 多字段同时回填
python scripts/backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail mkt_trend_strength
```

### 4.3 查看可回填字段

```python
# Python交互式
from monitor_bond import get_json_field_registry
registry = get_json_field_registry()
print("可回填字段:", list(registry.keys()))
for field, config in registry.items():
    print(f"  {field}: depends={config['depends']}")
```

---

## 五、版本迭代记录

### v1.0 - 初始方案（字段级独立更新）

**时间**：2026-07-23

**设计**：
- 计算逻辑分散在多处
- `backfill_json_fields.py` 独立实现计算
- 需要维护两套逻辑

**问题**：
- 违反"回填必须使用与实时计算完全一致的函数"原则
- 维护成本高

### v2.0 - 复用现有架构

**时间**：2026-07-23

**改进**：
- 计算逻辑统一放在 `monitor_bond.py`
- `compute_engine.py` 复用 `monitor_bond.py` 的函数
- 减少重复代码

**仍有问题**：
- 新增字段仍需修改3个文件
- 未实现"一次修改到处调用"

### v3.0 - 一次修改到处调用（最终版）

**时间**：2026-07-24

**核心改进**：
1. **字段注册表**（JSON_FIELD_REGISTRY）：集中配置所有JSON字段
2. **通用计算接口**（compute_json_field）：自动根据注册表调用计算函数
3. **compute_engine自动适配**：自动读取注册表，无需为每个字段写方法
4. **backfill_json_fields自动识别**：自动读取注册表，无需手动注册字段

**优势**：
- 新增字段只需修改1个文件（monitor_bond.py）
- 实时和回填共用同一套计算逻辑
- 扩展容易，错误减少

---

## 六、实施检查清单

### 6.1 一次性配置（建立机制）

- [ ] 修改 `monitor_bond.py` 添加 `JSON_FIELD_REGISTRY` 注册表
- [ ] 修改 `monitor_bond.py` 添加 `get_json_field_registry()` 接口
- [ ] 修改 `monitor_bond.py` 添加 `compute_json_field()` 通用接口
- [ ] 修改 `compute_engine.py` 添加自动读取注册表机制
- [ ] 修改 `compute_engine.py` 添加 `_compute_json_field()` 通用回填方法
- [ ] 修改 `backfill_json_fields.py` 自动读取注册表

### 6.2 新增形态字段（验证"一次修改"）

- [ ] 修改 `monitor_bond.py` 添加全局状态 `_mkt_shape_date`, `_mkt_shape_history`
- [ ] 修改 `monitor_bond.py` 添加计算函数 `compute_mkt_shape()`, `compute_mkt_shape_detail()`
- [ ] 修改 `monitor_bond.py` 在 `compute_mkt_trend_indicators()` 中调用形态计算
- [ ] 修改 `monitor_bond.py` 在 `JSON_FIELD_REGISTRY` 中注册新字段
- [ ] **验证**：`compute_engine.py` 和 `backfill_json_fields.py` **无需修改**

### 6.3 测试验证

- [ ] 测试实时形态计算
- [ ] 测试历史数据回填（自动识别新字段）
- [ ] 测试新增其他字段流程（验证"一次修改"机制）
- [ ] 测试字段逻辑更新（修改计算函数后重新回填）

---

## 七、未来扩展指南

### 7.1 新增JSON字段的标准流程

1. **在 monitor_bond.py 中添加**：
   - 全局状态变量（如果需要）
   - 计算函数（`compute_xxx`）
   - 实时调用（在 `compute_mkt_trend_indicators` 或其他函数中）
   - 注册表条目（在 `JSON_FIELD_REGISTRY` 中）

2. **验证**：
   - 实时计算：`python -c "from monitor_bond import compute_xxx; ..."`
   - 回填：`python backfill_json_fields.py --fields xxx`

3. **无需修改**：
   - `compute_engine.py`（自动支持）
   - `backfill_json_fields.py`（自动支持）

### 7.2 字段类型扩展

如果需要支持不同类型的字段：

```python
# 在注册表中增加 type 字段
JSON_FIELD_REGISTRY = {
    'mkt_shape': {
        'type': 'string',
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_shape',
        # ...
    },
    'mkt_trend_strength': {
        'type': 'float',
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_trend_strength',
        # ...
    },
}
```

### 7.3 跨日期字段

如果需要跨日期计算（如多日均线）：

```python
JSON_FIELD_REGISTRY = {
    'mkt_5day_avg': {
        'depends': ['mkt_vs_open_pct'],
        'computer': 'compute_mkt_5day_avg',
        'needs_history': True,
        'needs_cross_date': True,  # 标记需要跨日期数据
        'state_vars': ['_mkt_5day_cache'],
    },
}
```

---

## 八、总结

### 核心设计

**"一次修改到处调用"** 通过以下机制实现：

1. **集中配置**：所有字段配置在 `monitor_bond.py` 的 `JSON_FIELD_REGISTRY` 中
2. **通用接口**：`compute_json_field()` 自动根据注册表调用计算函数
3. **自动适配**：`compute_engine.py` 和 `backfill_json_fields.py` 自动读取注册表

### 关键优势

| 优势 | 说明 |
|------|------|
| **维护简单** | 新增字段只需修改1个文件 |
| **一致性保证** | 实时和回填共用同一套计算逻辑 |
| **扩展容易** | 添加新字段只需4步：状态+函数+实时调用+注册 |
| **错误减少** | 不需要在多个文件中同步修改 |
| **可追溯** | 所有字段配置在一个注册表中，易于管理 |

### 操作口诀

> **新增字段四步走**：
> 1. 状态变量放全局
> 2. 计算函数要纯函数
> 3. 实时计算里调用
> 4. 注册表中添条目
> 
> **其他文件不用动，自动识别真轻松！**

---

**文档版本**：v3.0（最终版）  
**最后更新**：2026-07-24  
**审核状态**：等待用户审核
