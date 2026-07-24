# backfill_json_fields.py 性能分析与优化方案

## 一、当前性能瓶颈分析

### 1.1 当前执行流程回顾

```
单日回填
  ├── 1. 预估总行数（1次查询）
  ├── 2. 时间分片读取（~48次查询，100tick/片）
  │   └── 每次查询：SELECT bond_code, time, ext_indicators FROM table WHERE time IN (...)
  ├── 3. 逐行处理（~20万行）
  │   ├── json.loads(ext_indicators)  # JSON解析
  │   ├── 状态更新
  │   ├── 字段计算（Python函数调用）
  │   └── 累积更新列表
  └── 4. 批量UPDATE（~4次，5万行/批次）
      └── 临时表+UPDATE JOIN
```

### 1.2 性能瓶颈识别

| 环节 | 当前实现 | 耗时估算 | 瓶颈程度 |
|------|---------|---------|---------|
| **时间分片读取** | 48次查询，每次100个时间点 | ~10-20s | 中 |
| **JSON解析** | 20万行 × json.loads() | ~5-10s | **高** |
| **逐行计算** | Python循环，逐行处理 | ~30-60s | **最高** |
| **状态更新** | 每行调用 _update_state() | ~5-10s | 高 |
| **字段计算** | Python函数调用，每字段 | ~10-20s | **高** |
| **批量UPDATE** | 4次批量UPDATE | ~5-10s | 低 |

**总耗时估算**：~60-120s/天

### 1.3 核心问题

1. **逐行处理**：Python循环处理20万行，无法利用向量化
2. **JSON解析**：每行都调用 json.loads()，重复解析
3. **函数调用开销**：每行、每字段都调用Python函数
4. **状态管理**：Python层面的状态更新，非向量化

## 二、优化方案（不影响计算逻辑）

### 核心原则
- **计算逻辑不变**：`monitor_bond.py` 的计算函数保持纯函数
- **优化数据处理**：在 `backfill_json_fields.py` 中优化数据读取和批量处理
- **减少Python开销**：向量化、减少循环、减少函数调用

### 方案1：向量化JSON解析（高优先级）

**问题**：每行调用 `json.loads()`，20万行 = 20万次解析

**优化**：使用 pandas 的 `apply` + 批量解析

```python
# 当前（慢）
for _, row in df.iterrows():
    ext = json.loads(row['ext_indicators'])
    ...

# 优化后（快5-10x）
# 批量解析JSON
df['ext_parsed'] = df['ext_indicators'].apply(
    lambda x: json.loads(x) if x else {}
)

# 向量化提取依赖字段
for dep in all_deps:
    df[f'dep_{dep}'] = df['ext_parsed'].apply(lambda x: x.get(dep))
```

**预期提升**：JSON解析 5-10x

### 方案2：批量状态更新（高优先级）

**问题**：每行调用 `_update_state()`，Python函数调用开销大

**优化**：批量状态更新，减少函数调用次数

```python
# 当前（慢）
for _, row in df.iterrows():
    deps = {dep: ext.get(dep) for dep in all_deps}
    compute_engine._update_state(deps)  # 每行调用

# 优化后（快3-5x）
# 批量更新状态（tick级别，非行级别）
for tick_time, df_tick in df.groupby('time'):
    # 该时间点的所有债券一起更新状态
    for _, row in df_tick.iterrows():
        deps = {dep: row[f'dep_{dep}'] for dep in all_deps}
        compute_engine._update_state(deps)
```

**预期提升**：状态更新 3-5x

### 方案3：预计算+缓存（中优先级）

**问题**：同一时间点，不同债券的依赖值可能相同，重复计算

**优化**：按时间点缓存依赖值

```python
# 添加缓存
deps_cache = {}

for tick_time, df_tick in df.groupby('time'):
    # 检查缓存
    cache_key = tick_time
    if cache_key not in deps_cache:
        # 计算该时间点的依赖值（取第一行）
        deps_cache[cache_key] = {
            dep: df_tick.iloc[0][f'dep_{dep}'] 
            for dep in all_deps
        }
    
    deps = deps_cache[cache_key]
    # 所有债券使用相同的依赖值（大盘指标）
```

**适用场景**：大盘指标（mkt_开头），所有债券共享

**预期提升**：计算 2-3x（仅大盘指标）

### 方案4：减少批次大小（低优先级）

**问题**：5万行/批次，内存占用大，单次UPDATE慢

**优化**：减小批次，增加批次数量

```python
# 当前
FLUSH_SIZE = 50000  # 5万行/批次

# 优化后
FLUSH_SIZE = 10000  # 1万行/批次
```

**权衡**：内存降低，但UPDATE次数增加

**预期提升**：内存降低50%，速度可能略降

### 方案5：异步UPDATE（中优先级）

**问题**：批量UPDATE时，计算暂停

**优化**：后台线程执行UPDATE，主线程继续计算

```python
import threading
from queue import Queue

update_queue = Queue()

def async_update_worker():
    while True:
        df_updates = update_queue.get()
        if df_updates is None:
            break
        _bulk_update_json_fields(engine, table_name, df_updates)

# 启动后台线程
threading.Thread(target=async_update_worker).start()

# 主线程计算，达到阈值时提交到队列
if len(all_updates) >= FLUSH_SIZE:
    update_queue.put(pd.DataFrame(all_updates))
    all_updates = []  # 立即清空，继续计算
```

**预期提升**：整体吞吐量 1.5-2x

## 三、推荐实施方案

### 阶段1：向量化优化（必须实施）

**修改内容**：
1. 批量JSON解析
2. 向量化提取依赖字段
3. 批量状态更新

**预期效果**：整体速度提升 3-5x（60s → 15-20s）

### 阶段2：异步UPDATE（可选）

**修改内容**：
1. 添加后台UPDATE线程
2. 队列管理

**预期效果**：整体吞吐量提升 1.5-2x

## 四、具体代码修改

### 4.1 向量化JSON解析

```python
def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                        all_deps: Set[str], skip_existing: bool):
    ...
    
    for df_batch in load_table_data_streaming(...):
        if df_batch.empty:
            continue
        
        # 【优化1】批量JSON解析（向量化）
        df_batch['ext_parsed'] = df_batch['ext_indicators'].apply(
            lambda x: json.loads(x) if x else {}
        )
        
        # 【优化2】向量化提取依赖字段
        for dep in all_deps:
            df_batch[dep] = df_batch['ext_parsed'].apply(lambda x: x.get(dep))
        
        # 【优化3】检查skip_existing（向量化）
        if skip_existing:
            df_batch['all_exist'] = df_batch['ext_parsed'].apply(
                lambda x: all(f in x for f in target_fields)
            )
            df_skip = df_batch[df_batch['all_exist']]
            df_calc = df_batch[~df_batch['all_exist']]
            
            # 批量更新跳过行的状态
            for _, row in df_skip.iterrows():
                deps = {dep: row[dep] for dep in all_deps}
                compute_engine._update_state(deps)
        else:
            df_calc = df_batch
        
        # 【优化4】批量计算
        for tick_time, df_tick in df_calc.groupby('time'):
            # 取第一行更新状态（大盘指标）
            first_row = df_tick.iloc[0]
            deps = {dep: first_row[dep] for dep in all_deps}
            compute_engine._update_state(deps)
            
            # 批量计算所有债券
            for _, row in df_tick.iterrows():
                for field_name in target_fields:
                    field_config = self.json_fields.get(field_name)
                    if not field_config:
                        continue
                    
                    # 构建历史
                    history = []
                    if field_config.get('needs_history'):
                        state_var = field_config.get('state_vars', [''])[0].lstrip('_')
                        history = getattr(compute_engine, state_var, [])
                        history = history[:-1] if len(history) > 1 else []
                    
                    # 计算
                    value = compute_engine._compute_json_field(field_name, deps, history)
                    
                    all_updates.append({
                        'bond_code': row['bond_code'],
                        'time': str(row['time']),
                        'field_name': field_name,
                        'field_value': json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                    })
```

## 五、性能对比预测

| 优化阶段 | 预估耗时 | 提升 |
|---------|---------|------|
| 当前 | ~60-120s | - |
| 阶段1（向量化） | ~15-30s | **4x** |
| 阶段2（异步UPDATE） | ~10-20s | **6x** |

## 六、不影响计算逻辑的保证

- ✅ `monitor_bond.py` 完全不变
- ✅ `compute_engine._compute_json_field()` 调用方式不变
- ✅ 计算结果与优化前完全一致
- ✅ 只优化数据处理和批量策略

---

**等待用户审核通过后实施。**
