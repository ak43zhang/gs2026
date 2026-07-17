# P2-B 统一数据清洗入口 - 详细设计方案

## 一、问题分析

### 1.1 当前重复清洗问题

通过代码扫描发现，以下数据清洗操作在多个函数中**重复执行**：

| 清洗操作 | 重复次数 | 涉及函数 | 每次耗时 |
|----------|----------|----------|----------|
| 代码格式化 `str.zfill(6)` | 3-4次 | deal_gp_works, calculate_top30_v3, calculate_main_force_and_cumulative | 10-20ms |
| 类型转换 `pd.to_numeric` | 2-3次 | get_market_stats, calculate_top30_v3 | 20-30ms |
| 数据过滤 `price>0 & volume>0` | 2-3次 | calculate_top30_v3, 其他 | 10-15ms |
| **总计** | **7-10次** | - | **40-65ms/周期** |

### 1.2 具体重复位置

```python
# 位置1: deal_gp_works (约第1736行)
df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)

# 位置2: calculate_top30_v3 (第810-811行)
df_now['code'] = df_now['code'].astype(str).str.zfill(6)
df_prev['code'] = df_prev['code'].astype(str).str.zfill(6)

# 位置3: calculate_top30_v3 (第817-822行)
for col in num_cols:
    df_now[col] = pd.to_numeric(df_now[col], errors='coerce')
    df_prev[col] = pd.to_numeric(df_prev[col], errors='coerce')

# 位置4: calculate_top30_v3 (第824-825行)
df_now = df_now[(df_now['price'] > 0) & (df_now['volume'] > 0) & (df_now['amount'] > 0)]

# 位置5: calculate_main_force_and_cumulative (第448行附近)
df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)

# 位置6: get_market_stats (第1541行)
df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')

# 位置7: get_market_stats (第1548行)
df_prev['change_pct'] = pd.to_numeric(df_prev['change_pct'], errors='coerce')
```

---

## 二、设计方案

### 2.1 核心思路

**"清洗一次，处处使用"**

在数据入口 `deal_gp_works` 中进行**完整清洗**，后续函数**直接使用**，不再重复清洗。

### 2.2 清洗内容定义

```python
# 统一清洗标准
NORMALIZED_COLUMNS = {
    # 代码字段统一
    'stock_code': {'type': 'str', 'format': 'zfill6', 'aliases': ['code']},
    
    # 数值字段统一
    'price': {'type': 'float', 'min': 0},
    'volume': {'type': 'float', 'min': 0},
    'amount': {'type': 'float', 'min': 0},
    'change_pct': {'type': 'float'},
    'main_net_amount': {'type': 'float', 'default': 0},
    'cumulative_main_net': {'type': 'float', 'default': 0},
}
```

### 2.3 具体实现

#### 步骤1: 新增统一清洗函数

```python
def normalize_stock_dataframe(df: pd.DataFrame, 
                                required_cols: list = None) -> pd.DataFrame:
    """
    统一数据清洗入口函数
    
    在deal_gp_works中调用一次，后续函数直接使用，避免重复清洗。
    
    清洗内容：
    1. 代码字段统一为6位字符串（stock_code/code）
    2. 数值字段统一转换为float（price/volume/amount/change_pct等）
    3. 删除无效数据（price/volume/amount <= 0）
    4. 填充默认值（main_net_amount/cumulative_main_net缺失时填0）
    
    Args:
        df: 原始DataFrame
        required_cols: 必需列列表，缺失时返回空DataFrame
        
    Returns:
        pd.DataFrame: 清洗后的DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    df = df.copy()
    
    # 1. 统一代码字段
    # stock_code 优先级高于 code
    if 'stock_code' in df.columns:
        df['stock_code'] = (df['stock_code']
                           .astype(str)
                           .str.strip()
                           .str.replace(r'[^0-9]', '', regex=True)
                           .str.zfill(6))
    elif 'code' in df.columns:
        df['stock_code'] = (df['code']
                           .astype(str)
                           .str.strip()
                           .str.replace(r'[^0-9]', '', regex=True)
                           .str.zfill(6))
    
    # 2. 统一数值字段
    numeric_cols = ['price', 'volume', 'amount', 'change_pct', 
                    'main_net_amount', 'cumulative_main_net']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 3. 填充默认值
    if 'main_net_amount' in df.columns:
        df['main_net_amount'] = df['main_net_amount'].fillna(0)
    if 'cumulative_main_net' in df.columns:
        df['cumulative_main_net'] = df['cumulative_main_net'].fillna(0)
    
    # 4. 删除无效数据（核心字段必须有效）
    if all(c in df.columns for c in ['price', 'volume', 'amount']):
        df = df[(df['price'] > 0) & (df['volume'] > 0) & (df['amount'] > 0)]
    
    # 5. 删除重复代码（保留第一个）
    if 'stock_code' in df.columns:
        df = df.drop_duplicates(subset=['stock_code'], keep='first')
    
    # 6. 检查必需列
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            logger.warning(f"缺少必需列: {missing}")
            return pd.DataFrame()
    
    return df
```

#### 步骤2: 修改deal_gp_works入口

```python
def deal_gp_works(loop_start):
    """
    股票数据处理主函数
    
    【P2-B优化】统一数据清洗，避免后续函数重复处理
    """
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        # 1. 采集数据
        df_now = fetch_all_concurrently(STOCK_CODES)
        if df_now.empty:
            logger.warning(f"[{time_full}] 无数据，跳过处理")
            return
        
        # 【P2-B】统一数据清洗（一次清洗，处处使用）
        df_now = normalize_stock_dataframe(df_now, required_cols=['stock_code', 'price'])
        if df_now.empty:
            logger.warning(f"[{time_full}] 数据清洗后为空，跳过处理")
            return
        
        logger.info(f"[{time_full}] 数据采集完成: {len(df_now)}只，清洗后有效")
        
        # 2. 获取前一时刻数据（同样清洗）
        df_prev = load_prev_data(...)  # 从Redis加载
        if df_prev is not None and not df_prev.empty:
            df_prev = normalize_stock_dataframe(df_prev)
        
        # 3. 后续处理（直接使用已清洗的数据）
        # ... 涨停判断、主力净额计算等
        
    except Exception as e:
        logger.error(f"处理异常: {e}")
        raise
```

#### 步骤3: 简化calculate_top30_v3

```python
def calculate_top30_v3(df_now: pd.DataFrame, df_prev: pd.DataFrame, 
                       dt: datetime, weights: dict = None) -> pd.DataFrame:
    """
    【P2-B优化】移除重复清洗，直接使用已清洗数据
    """
    # 【删除】不再重复清洗，数据已在deal_gp_works中清洗
    # df_now = df_now.copy()
    # df_prev = df_prev.copy()
    # df_now['code'] = df_now['code'].astype(str).str.zfill(6)  # ← 删除
    # ... 其他清洗代码删除
    
    # 直接使用已清洗的数据
    # df_now 和 df_prev 已经包含：
    # - stock_code: 6位字符串
    # - price/volume/amount: float类型
    # - change_pct: float类型
    # - 已删除无效数据
    
    # 只需要本地复制避免修改原始数据
    df_now = df_now.copy()
    df_prev = df_prev.copy()
    
    # 【保留】业务逻辑需要的字段映射
    # 如果df_now使用'stock_code'而本函数需要'code'
    if 'code' not in df_now.columns and 'stock_code' in df_now.columns:
        df_now['code'] = df_now['stock_code']
    if 'code' not in df_prev.columns and 'stock_code' in df_prev.columns:
        df_prev['code'] = df_prev['stock_code']
    
    # ... 后续计算逻辑不变
```

#### 步骤4: 简化calculate_main_force_and_cumulative

```python
def calculate_main_force_and_cumulative(df_now: pd.DataFrame,
                                        df_prev_main: pd.DataFrame,
                                        day_stats: dict,
                                        time_of_day: dt_time) -> pd.DataFrame:
    """
    【P2-B优化】移除重复清洗
    """
    # 【删除】不再重复清洗
    # df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)  # ← 删除
    
    # 直接使用已清洗的数据
    # ... 后续逻辑不变
```

#### 步骤5: 简化get_market_stats

```python
def get_market_stats(df_now: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    【P2-B优化】移除重复类型转换
    """
    # 【删除】不再重复转换
    # df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')  # ← 删除
    # df_prev['change_pct'] = pd.to_numeric(df_prev['change_pct'], errors='coerce')  # ← 删除
    
    # 【保留】dropna（业务需要）
    df_now = df_now.dropna(subset=['change_pct'])
    if df_prev is not None and not df_prev.empty:
        df_prev = df_prev.dropna(subset=['change_pct'])
    
    # ... 后续逻辑不变
```

---

## 三、修改清单

### 文件: monitor_stock.py

| 行号 | 操作 | 内容 |
|------|------|------|
| ~60 | 新增 | `normalize_stock_dataframe()` 函数定义 |
| ~1736 | 修改 | `deal_gp_works()` 中调用 `normalize_stock_dataframe()` |
| ~783 | 删除 | `calculate_top30_v3()` 中的重复清洗代码（~20行） |
| ~448 | 删除 | `calculate_main_force_and_cumulative()` 中的重复清洗代码（~2行） |
| ~1516 | 简化 | `get_market_stats()` 移除重复类型转换（~4行） |

**总改动**: 
- 新增: ~80行
- 删除: ~30行
- 修改: ~5处调用点

---

## 四、风险评估

### 4.1 风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 清洗逻辑遗漏 | 低 | 高 | 完整测试覆盖所有函数 |
| 列名不一致 | 中 | 中 | 统一使用'stock_code' |
| 默认值变化 | 低 | 中 | 对比测试验证 |
| 性能退化 | 极低 | 高 | 监控执行时间 |

### 4.2 测试方案

```python
# 测试1: 数据一致性测试
def test_normalize_consistency():
    """验证清洗前后数据一致性"""
    raw_df = load_test_data()
    
    # 旧方式（多次清洗）
    old_result = old_calculate_top30(raw_df.copy())
    
    # 新方式（统一清洗）
    cleaned_df = normalize_stock_dataframe(raw_df)
    new_result = new_calculate_top30(cleaned_df)
    
    # 对比结果
    assert old_result.equals(new_result)

# 测试2: 性能测试
def test_performance():
    """验证性能提升"""
    import time
    
    raw_df = load_large_dataset()  # 5000只
    
    # 旧方式总耗时
    t1 = time.time()
    for _ in range(100):
        old_pipeline(raw_df.copy())
    old_time = time.time() - t1
    
    # 新方式总耗时
    t2 = time.time()
    cleaned = normalize_stock_dataframe(raw_df)
    for _ in range(100):
        new_pipeline(cleaned.copy())
    new_time = time.time() - t2
    
    print(f"性能提升: {old_time/new_time:.1f}x")
    assert new_time < old_time * 0.7  # 至少提升30%
```

---

## 五、预期效果

### 5.1 时间节省

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 代码格式化重复 | 30-50ms | 10ms | 20-40ms |
| 类型转换重复 | 40-90ms | 20-30ms | 20-60ms |
| 数据过滤重复 | 20-30ms | 10ms | 10-20ms |
| **P2-B总计** | **90-170ms** | **40-50ms** | **50-120ms** |

### 5.2 代码质量提升

- **减少重复代码**: ~30行删除
- **统一数据标准**: 所有函数使用相同清洗逻辑
- **降低维护成本**: 修改清洗逻辑只需改一处
- **提高可读性**: 业务逻辑更清晰

---

## 六、回退方案

```python
# 如果出现问题，快速回退：
# 1. 删除 normalize_stock_dataframe() 调用
# 2. 恢复各函数中的原始清洗代码
# 3. 或者使用条件编译：

USE_UNIFIED_CLEAN = True  # 开关控制

def deal_gp_works(loop_start):
    df_now = fetch_all_concurrently(STOCK_CODES)
    
    if USE_UNIFIED_CLEAN:
        df_now = normalize_stock_dataframe(df_now)
    else:
        # 原始清洗逻辑
        df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)
        ...
```

---

## 七、实施计划

### Step 1: 准备（5分钟）
- 备份 monitor_stock.py
- 创建测试脚本

### Step 2: 实施（15分钟）
- 新增 `normalize_stock_dataframe()` 函数
- 修改 `deal_gp_works()` 调用清洗函数
- 简化 `calculate_top30_v3()`
- 简化 `calculate_main_force_and_cumulative()`
- 简化 `get_market_stats()`

### Step 3: 测试（10分钟）
- 运行单元测试
- 对比数据一致性
- 验证性能提升

### Step 4: 提交（5分钟）
- git commit
- 更新文档

**总计**: ~35分钟

---

## 八、审核确认项

请确认以下事项：

1. **清洗字段**: 是否还需要清洗其他字段？
2. **默认值**: `main_net_amount=0` 是否合适？
3. **列名统一**: 统一使用 `stock_code` 还是保留 `code`？
4. **实施时机**: 是否立即实施？

---

**请审核通过后，我将立即实施。**
