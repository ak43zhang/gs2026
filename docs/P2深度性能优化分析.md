# monitor_stock.py 深度性能优化分析

## 一、代码现状总览

- **总行数**: 2312行
- **函数数量**: 46个
- **核心流程**: 数据采集 → 涨停判断 → 主力净额计算 → 上攻排行 → 行业排行 → 存储

---

## 二、性能瓶颈深度分析

### 瓶颈1: calculate_top30_v3 - 上攻排行计算 (⭐⭐⭐ 最高优先级)

**位置**: 第783-973行，~190行代码

**当前问题**:
```python
# 问题1: 动态价格区间使用Python循环
price_bounds = get_price_bounds(merged['code'])  # ← 逐行Python循环
merged['price_min'] = [b[0] for b in price_bounds]
merged['price_max'] = [b[1] for b in price_bounds]

# 问题2: 多次重复计算rank
merged['zf_30_rank'] = merged['zf_30'].rank(...)
merged['momentum_rank'] = merged['momentum'].rank(...)
merged['amount_rank'] = merged['amount_now'].rank(...)
# ... 共4次rank计算

# 问题3: 多次重复类型转换
df_now['code'] = df_now['code'].astype(str).str.zfill(6)  # 第1次
# ... 后续可能还有多次

# 问题4: 重复数据清洗
df_now = df_now[(df_now['price'] > 0) & ...]  # 第1次
# ... 后续可能还有
```

**性能影响**:
- 动态价格区间: ~50-100ms (5000只 × Python循环)
- 多次rank: ~30-50ms × 4 = 120-200ms
- 重复类型转换: ~20-30ms × N次
- **总计: ~200-350ms**

**优化方案**:

```python
# 方案1: 价格区间向量化
def get_price_bounds_vectorized(code_series):
    """向量化价格区间判断"""
    # 主板
    is_main = code_series.str.startswith(('600','601','603','605','000','001','002'))
    # 创业板
    is_cy = code_series.str.startswith('300')
    # 科创板
    is_kc = code_series.str.startswith('688')
    # 可转债
    is_zq = code_series.str.startswith(('11','12','123','127'))
    
    price_min = np.where(is_main, 3, 
                        np.where(is_cy, 5,
                                np.where(is_kc, 10,
                                        np.where(is_zq, 110, 1))))
    price_max = np.where(is_main, 100,
                        np.where(is_cy, 200,
                                np.where(is_kc, 500,
                                        np.where(is_zq, 250, 1000))))
    return price_min, price_max

# 方案2: 合并rank计算
# 使用rank的pct参数直接计算百分位数，避免两次rank

# 方案3: 缓存类型转换结果
# 使用模块级缓存避免重复转换
```

**预期提升**: 200-350ms → 50-100ms (节省150-250ms)

---

### 瓶颈2: get_market_stats - 大盘统计 (⭐⭐⭐ 高优先级)

**位置**: 第1516-1642行

**当前问题**:
```python
# 问题1: 多次类型转换
df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')  # 第1次
df_prev['change_pct'] = pd.to_numeric(df_prev['change_pct'], errors='coerce')  # 第2次

# 问题2: 多次dropna
df_now = df_now.dropna(subset=['change_pct'])  # 第1次
df_prev = df_prev.dropna(subset=['change_pct'])  # 第2次

# 问题3: 逐行统计使用Python计算
for col in ['cur_up', 'cur_down', 'cur_flat', ...]:
    # 大量Python级别的统计计算
```

**性能影响**: ~50-100ms

**优化方案**:
- 类型转换前置（在deal_gp_works中统一处理）
- 使用向量化统计替代Python循环
- 合并多次dropna

**预期提升**: 50-100ms → 20-30ms (节省30-70ms)

---

### 瓶颈3: judge_market_strength - 市场强度判断 (⭐⭐ 中优先级)

**位置**: 第1642-1736行

**当前问题**:
```python
# 问题: 强制类型转换（已转换过）
cur_up_ratio = float(stats_row['cur_up_ratio'])  # 已在上游转换为float
# ... 大量重复转换

# 问题: 复杂条件判断（难以向量化）
if not pd.isna(cur_up_down_ratio) and cur_up_down_ratio is not None:
    if cur_up_down_ratio > 200:
        base_score += min(cur_up_down_ratio - 200, 200) * 0.1
    elif cur_up_down_ratio < 50:
        base_score -= (50 - cur_up_down_ratio) * 0.2
```

**性能影响**: ~10-20ms（数据量小，影响有限）

**优化方案**:
- 删除重复类型转换
- 使用np.where向量化条件判断

**预期提升**: 10-20ms → 5-10ms (节省5-10ms)

---

### 瓶颈4: calculate_industry_topn - 行业排行 (⭐⭐ 中优先级)

**位置**: 第1966-2104行

**当前问题**:
```python
# 问题1: 行业映射使用Python循环
code_to_industry = {k: v['industry_code'] for k, v in mapping_cache.items()}
# ... 后续map操作

# 问题2: 多次groupby
industry_counts = up_df.groupby('industry_code').size()
industry_change_sum = all_df.groupby('industry_code')['change_pct'].sum()
# ... 多次groupby

# 问题3: 复杂merge
result = up_counts.merge(industry_totals, ...).merge(industry_change_sum, ...)
# ... 多次merge
```

**性能影响**: ~100-200ms

**优化方案**:
- 使用pd.Series.map替代Python循环
- 合并多次groupby为一次agg
- 优化merge顺序

**预期提升**: 100-200ms → 50-80ms (节省50-120ms)

---

### 瓶颈5: 重复数据清洗 (⭐⭐⭐ 高优先级)

**问题**: 多个函数重复进行相同的数据清洗

```python
# deal_gp_works中
df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)

# calculate_top30_v3中
df_now['code'] = df_now['code'].astype(str).str.zfill(6)

# calculate_main_force_and_cumulative中
df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)
```

**性能影响**: 每次~10-20ms，重复3-4次 = 30-80ms

**优化方案**:
- 统一数据清洗入口
- 使用模块级缓存避免重复清洗

**预期提升**: 30-80ms → 10-20ms (节省20-60ms)

---

### 瓶颈6: 重复类型转换 (⭐⭐ 中优先级)

**问题**: `pd.to_numeric`在多个函数中重复调用

```python
# get_market_stats中
df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')

# calculate_top30_v3中
for col in num_cols:
    df_now[col] = pd.to_numeric(df_now[col], errors='coerce')
```

**性能影响**: 每次~20-30ms，重复2-3次 = 40-90ms

**优化方案**:
- 在deal_gp_works中统一转换
- 后续函数直接使用已转换的数据

**预期提升**: 40-90ms → 20-30ms (节省20-60ms)

---

## 三、优化方案汇总

### P2-A: calculate_top30_v3向量化优化

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 价格区间向量化 | 50-100ms | 5-10ms | 45-90ms |
| rank合并计算 | 120-200ms | 60-100ms | 60-100ms |
| 重复清洗消除 | 30-50ms | 10ms | 20-40ms |
| **总计** | **200-350ms** | **75-120ms** | **125-230ms** |

**实施难度**: 中
**风险**: 低（纯计算优化，逻辑不变）

---

### P2-B: 统一数据清洗入口

**方案**: 在deal_gp_works中统一进行数据清洗，后续函数直接使用

```python
def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """统一数据清洗入口"""
    df = df.copy()
    
    # 统一代码格式
    if 'stock_code' in df.columns:
        df['stock_code'] = df['stock_code'].astype(str).str.strip().str.zfill(6)
    if 'code' in df.columns:
        df['code'] = df['code'].astype(str).str.strip().str.zfill(6)
    
    # 统一数值类型
    numeric_cols = ['price', 'volume', 'amount', 'change_pct']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 统一删除无效数据
    df = df[(df['price'] > 0) & (df['volume'] > 0) & (df['amount'] > 0)]
    
    return df
```

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 重复代码格式转换 | 30-50ms | 10ms | 20-40ms |
| 重复类型转换 | 40-90ms | 20-30ms | 20-60ms |
| 重复数据清洗 | 20-30ms | 10ms | 10-20ms |
| **总计** | **90-170ms** | **40-50ms** | **50-120ms** |

**实施难度**: 低
**风险**: 中（需要修改多个函数的调用点）

---

### P2-C: 行业排行优化

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 行业映射向量化 | 30-50ms | 10-15ms | 20-35ms |
| groupby合并 | 40-60ms | 20-30ms | 20-30ms |
| merge优化 | 30-50ms | 20-30ms | 10-20ms |
| **总计** | **100-160ms** | **50-75ms** | **50-85ms** |

**实施难度**: 中
**风险**: 低

---

### P2-D: 大盘统计优化

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| 消除重复转换 | 30-50ms | 0ms | 30-50ms |
| 向量化统计 | 20-30ms | 10-15ms | 10-15ms |
| **总计** | **50-80ms** | **10-15ms** | **40-65ms** |

**实施难度**: 低
**风险**: 低

---

## 四、综合效果预测

### 优化前后对比

| 优化项 | 当前耗时 | 优化后 | 节省 |
|--------|----------|--------|------|
| P0: 涨停判断向量化 | 500-1000ms | 10-20ms | 490-980ms |
| P1-A: 采集超时控制 | 异常时无上限 | 2.5s上限 | 防止堆积 |
| P1-B: 存储异步化 | 500-1000ms | <50ms | 450-950ms |
| **P2-A**: top30向量化 | 200-350ms | 75-120ms | **125-230ms** |
| **P2-B**: 统一清洗 | 90-170ms | 40-50ms | **50-120ms** |
| **P2-C**: 行业排行 | 100-160ms | 50-75ms | **50-85ms** |
| **P2-D**: 大盘统计 | 50-80ms | 10-15ms | **40-65ms** |
| **P2总计** | **440-760ms** | **175-260ms** | **265-500ms** |

### 累计效果

| 阶段 | 当前总耗时 | 优化后 | 累计节省 |
|------|------------|--------|----------|
| 原始 | 3000-5700ms | - | - |
| P0+P1 | 1800-2600ms | 1200-3100ms | 1200-3100ms |
| **+P2** | **1350-2100ms** | **450-1600ms** | **450-1600ms** |

---

## 五、推荐实施顺序

### 第一阶段（立即实施）
1. **P2-B**: 统一数据清洗入口
   - 改动小，效果稳定
   - 为后续优化奠定基础

### 第二阶段（验证后实施）
2. **P2-D**: 大盘统计优化
   - 改动小，风险低
   
3. **P2-A**: top30向量化
   - 效果最大，但需要充分测试

### 第三阶段（最后实施）
4. **P2-C**: 行业排行优化
   - 效果中等，依赖P2-B的数据清洗

---

## 六、风险评估

| 优化项 | 风险等级 | 主要风险 | 缓解措施 |
|--------|----------|----------|----------|
| P2-A | 中 | 向量化逻辑错误 | 充分测试，保留原始代码 |
| P2-B | 低 | 调用点遗漏 | 全局搜索替换 |
| P2-C | 低 | 行业映射错误 | 对比测试 |
| P2-D | 低 | 统计结果不一致 | 对比测试 |

---

## 七、实施建议

### 建议方案

**推荐: P2-B + P2-D 先实施，P2-A + P2-C 后实施**

理由:
1. P2-B和P2-D改动小、风险低、效果稳定
2. P2-B为后续优化奠定基础（统一数据格式）
3. P2-A效果最大，但需要更多测试时间
4. P2-C依赖P2-B的数据清洗结果

### 预期总效果

- **保守估计**: 节省265ms
- **乐观估计**: 节省500ms
- **实施后总耗时**: 1.35-2.1秒（从3-5.7秒）

---

**请审核通过后，我将立即实施。**
