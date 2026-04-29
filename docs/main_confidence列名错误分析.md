# 主力净额计算 - main_confidence列名错误分析与修复

## 错误信息
```
计算主力净额失败: "['main_confidence'] not in index"
```

## 问题分析

### 错误位置
`monitor_stock.py` 第556行

### 代码对比

**valid_data中的列名**（第537-539行）：
```python
valid_data['main_behavior'] = behavior_results.apply(lambda x: x['type'])
valid_data['direction'] = behavior_results.apply(lambda x: x['direction'])
valid_data['confidence'] = behavior_results.apply(lambda x: x['confidence'])  # ← 列名是 confidence
```

**result_cols中的列名**（第556行）：
```python
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'main_confidence']  # ← 写的是 main_confidence
```

### 问题
`valid_data` 中实际列名是 `confidence`，但 `result_cols` 写的是 `main_confidence`，导致列名不匹配。

## 修复方案

### 方案A：修改result_cols（推荐）

将 `main_confidence` 改为 `confidence`：

```python
# 修复前
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'main_confidence']

# 修复后
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'confidence']
```

### 方案B：修改valid_data列名

将 `confidence` 改为 `main_confidence`：

```python
# 修复前
valid_data['confidence'] = behavior_results.apply(lambda x: x['confidence'])

# 修复后
valid_data['main_confidence'] = behavior_results.apply(lambda x: x['confidence'])
```

## 推荐方案

**方案A** - 修改result_cols

理由：
1. `main_behavior` 和 `confidence` 都是临时计算字段，不需要统一前缀
2. 修改一行即可，影响最小
3. 与后续 `fillna` 代码一致（第559行用 `main_confidence` 作为目标列名）

## 完整代码流程检查

### 检查点1：初始化字段 ✓
```python
df_now['main_net_amount'] = 0.0
df_now['main_behavior'] = '无主力'
df_now['main_confidence'] = 0.0
df_now['cumulative_main_net'] = 0.0
```

### 检查点2：数据清洗 ✓
```python
# stock_code格式化
df_now['stock_code'] = df_now['stock_code'].astype(str).str.strip().str.zfill(6)
df_prev_main['stock_code'] = df_prev_main['stock_code'].astype(str).str.strip().str.zfill(6)

# "-"转为0
if 'cumulative_main_net' in df_prev_main.columns:
    df_prev_main['cumulative_main_net'] = pd.to_numeric(...).fillna(0)
if 'main_net_amount' in df_prev_main.columns:
    df_prev_main['main_net_amount'] = pd.to_numeric(...).fillna(0)

# 数值字段转换
numeric_cols = ['price', 'volume', 'amount', 'change_pct']
for col in numeric_cols:
    ...
```

### 检查点3：合并计算 ✓
```python
merged = pd.merge(
    df_now[['stock_code', 'short_name', 'price', 'volume', 'amount', 'change_pct', 'is_zt']],
    df_prev_main[['stock_code', 'volume', 'amount', 'change_pct']],
    on='stock_code',
    suffixes=('_now', '_prev'),
    how='inner'
)
```

### 检查点4：变化量计算 ✓
```python
merged['delta_amount'] = merged['amount_now'] - merged['amount_prev']
merged['delta_volume'] = merged['volume_now'] - merged['volume_prev']
merged['price_change_pct'] = merged['change_pct_now'] - merged['change_pct_prev']
```

### 检查点5：门槛过滤 ✓
```python
mask = (merged['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']) & \
       (merged['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume'])
valid_data = merged[mask].copy()
```

### 检查点6：主力行为判断 ✓
```python
behavior_results = valid_data.apply(
    lambda row: classify_main_force_behavior(...), axis=1
)
valid_data['main_behavior'] = behavior_results.apply(lambda x: x['type'])
valid_data['direction'] = behavior_results.apply(lambda x: x['direction'])
valid_data['confidence'] = behavior_results.apply(lambda x: x['confidence'])
```

### 检查点7：参与系数和主力净额 ✓
```python
valid_data['participation'] = valid_data['delta_amount'].apply(calculate_participation_ratio)
valid_data['main_net_amount'] = (
    valid_data['delta_amount'] *
    valid_data['participation'] *
    valid_data['direction'] *
    valid_data['confidence']
).round(2)
```

### 检查点8：合并结果 ✗
```python
# 错误
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'main_confidence']

# 正确
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'confidence']
```

### 检查点9：填充缺失值 ✓
```python
df_now['main_net_amount'] = df_now['main_net_amount'].fillna(0)
df_now['main_behavior'] = df_now['main_behavior'].fillna('无主力')
df_now['main_confidence'] = df_now['main_confidence'].fillna(0)
```

### 检查点10：累计主力净额 ✓
```python
if 'cumulative_main_net' in df_prev_main.columns:
    prev_cumulative = df_prev_main[df_prev_main['cumulative_main_net'] != 0][['stock_code', 'cumulative_main_net']].copy()
    ...
```

## 修复实施

### 修改位置
`monitor_stock.py` 第556行

### 修改内容
```python
# 修复前
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'main_confidence']

# 修复后
result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'confidence']
```

## 审核确认

- [x] 问题：main_confidence列名不匹配
- [x] 根因：valid_data中是confidence，result_cols写的是main_confidence
- [x] 方案：修改result_cols为confidence
- [x] 流程检查：除第8点外，其他逻辑正确
- [ ] 等待用户审核通过
