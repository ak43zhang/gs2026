# calculate_industry_topn 函数优化方案

> 文档版本：v1.0  
> 创建日期：2026-04-10  
> 文件路径：`src/gs2026/monitor/monitor_stock.py` 第1005行

---

## 一、现有函数流程

### 1.1 数据流

```
deal_gp_works()
  │
  ├─ fetch_all_concurrently(STOCK_CODES)
  │   → df_now: [stock_code, short_name, price, change, change_pct, volume, amount]
  │
  ├─ calculate_top30_v3(df_now, df_prev, ...)
  │   → top30_df: [code, name, zf_30, momentum, ..., total_score, rq, time]
  │   （注意：不含 price 列）
  │
  └─ industry_attack(top30_df, df_now, ...)
      └─ calculate_industry_topn(stock_df=top30_df, all_stock_df=df_now, ...)
          └─ 输出: [code, name, count, total, avg_change_pct, raw_ratio, smooth_ratio,
                     confidence, final_score, rank, rq, time]
```

### 1.2 当前评分公式

```
final_score = smooth_ratio × confidence

其中：
  smooth_ratio = (上涨数 + 2) / (总数 + 20)       ← 贝叶斯平滑
  confidence   = f(total)                           ← 样本量置信度
    - total < 20:   0.6 + 0.2 × total/20
    - 20 ≤ total < 100: 0.8 + 0.15 × (total-20)/80
    - total ≥ 100:  min(1.0, 0.95 + 0.05 × (total-100)/100)
```

### 1.3 问题分析

**当前评分只考虑"上涨数量比例"和"样本量"，忽略了价格质量维度。**

典型问题场景：
- 某行业有50只股票，平均价格仅3.2元（多为低价股/ST擦边股），20只上涨
- 另一行业有30只股票，平均价格28.5元（正常蓝筹/成长股），12只上涨
- 按当前公式：行业A得分更高（上涨比例40% vs 40%，但样本量大→置信度高）
- **问题**：低价股波动性大、涨跌容易，上涨并不代表真实的资金流入强度

---

## 二、优化方案：引入价格质量因子

### 2.1 核心思路

在 `final_score` 计算中引入**价格质量因子（price_quality）**，降低低价股行业的得分权重，提升中高价股行业的排名公正性。

### 2.2 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `avg_price` | float | 行业均价（该行业所有股票的平均价格） |
| `price_quality` | float | 价格质量因子（0.5~1.0，均价越高越接近1.0） |

### 2.3 价格质量因子计算

采用 **S型压缩函数（Sigmoid变体）**，将均价映射到 [0.5, 1.0] 区间：

```python
price_quality = 0.5 + 0.5 × (1 - exp(-avg_price / K))
```

其中 `K` 为半衰期参数，控制衰减速度。

**参数设计依据**（A股价格分布）：

| 均价区间 | 典型行业 | price_quality | 说明 |
|---------|---------|---------------|------|
| 0~5元 | ST概念、低价股密集行业 | 0.50~0.63 | 严重惩罚 |
| 5~10元 | 部分周期股、传统制造 | 0.63~0.73 | 中等惩罚 |
| 10~20元 | 主流行业（银行、地产等） | 0.73~0.84 | 轻微惩罚 |
| 20~50元 | 成长行业（半导体、新能源等） | 0.84~0.95 | 基本无影响 |
| 50元以上 | 高端消费、创新药等 | 0.95~1.00 | 满分 |

**推荐 K=15**（当均价=15元时，price_quality ≈ 0.82，这是A股中位数附近）

### 2.4 新评分公式

```
final_score = smooth_ratio × confidence × price_quality^α
```

其中 `α` 为价格因子权重指数，控制价格因子的影响强度：
- `α = 0`：完全不考虑价格（退化为原始公式，向后兼容）
- `α = 0.5`：温和影响（推荐默认值）
- `α = 1.0`：标准影响
- `α > 1.0`：强烈惩罚低价行业

**推荐 α=0.5**，即取 `price_quality` 的平方根，避免过度惩罚：

```python
# α=0.5 时的实际效果：
# 均价3元行业:  price_quality=0.59, factor=0.59^0.5=0.77 → 得分打77折
# 均价10元行业: price_quality=0.74, factor=0.74^0.5=0.86 → 得分打86折
# 均价25元行业: price_quality=0.88, factor=0.88^0.5=0.94 → 几乎无影响
# 均价50元行业: price_quality=0.96, factor=0.96^0.5=0.98 → 无影响
```

### 2.5 函数签名变更

```python
def calculate_industry_topn(
    stock_df: pd.DataFrame,
    all_stock_df: pd.DataFrame,
    date_str: str,
    time_full: str,
    min_industry_return: float = 0,
    price_half_life: float = 15.0,    # 新增：价格半衰期参数K
    price_weight: float = 0.5         # 新增：价格因子权重指数α
) -> pd.DataFrame:
```

### 2.6 输出字段变更

新增两个字段，追加在原有字段之后：

```python
# 原有
['code', 'name', 'count', 'total', 'avg_change_pct',
 'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time']

# 新增
['code', 'name', 'count', 'total', 'avg_change_pct', 'avg_price', 'price_quality',
 'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time']
```

### 2.7 下游兼容性分析

| 下游消费者 | 影响 | 说明 |
|-----------|------|------|
| `save_dataframe()` → MySQL | ✅ 自动适配 | `to_sql` 自动处理新列 |
| `update_rank_redis()` | ✅ 无影响 | 只读 `code`/`name` 列 |
| `save_rank_to_mysql()` | ✅ 无影响 | 只读排行结果 |
| Dashboard 前端 | ✅ 无影响 | 前端读 Redis 排行，不读这些字段 |
| 日志输出 | 📝 需更新 | 新增 avg_price 和 price_quality 到日志 |

---

## 三、代码优化方案

### 3.1 提取结果列常量

**现状**：5处硬编码相同的列名列表  
**优化**：提取为模块级常量

```python
INDUSTRY_RESULT_COLUMNS = [
    'code', 'name', 'count', 'total', 'avg_change_pct', 'avg_price', 'price_quality',
    'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time'
]
```

### 3.2 提取缓存刷新逻辑

**现状**：缓存为空时3层if嵌套 + 全局变量操作（约25行）  
**优化**：提取为独立函数

```python
def _ensure_industry_mapping(time_full: str) -> dict:
    """确保行业映射缓存可用，必要时从Redis加载或初始化"""
    mapping = get_industry_mapping_cached()
    if mapping:
        return mapping
    
    logger.warning(f"[{time_full}] 行业映射缓存为空，尝试刷新...")
    global _industry_mapping_cache, _industry_mapping_cache_time
    _industry_mapping_cache = None
    _industry_mapping_cache_time = 0
    mapping = get_industry_mapping_cached()
    if mapping:
        return mapping
    
    logger.warning(f"[{time_full}] Redis中无行业映射数据，调用初始化...")
    from gs2026.utils.redis_util import init_stock_industry_mapping_to_redis
    if init_stock_industry_mapping_to_redis():
        _industry_mapping_cache = None
        _industry_mapping_cache_time = 0
        mapping = get_industry_mapping_cached()
        if mapping:
            logger.info(f"[{time_full}] 行业映射初始化成功，共 {len(mapping)} 条")
    
    return mapping or {}
```

### 3.3 提取列名标准化函数

**现状**：`all_df` 和 `stock_df_processed` 各写一遍相同的rename逻辑（约8行×2）  
**优化**：

```python
def _normalize_stock_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化股票DataFrame列名：stock_code→code, short_name→name, code补零6位"""
    result = df.copy()
    if 'stock_code' in result.columns and 'code' not in result.columns:
        result = result.rename(columns={'stock_code': 'code'})
    if 'short_name' in result.columns and 'name' not in result.columns:
        result = result.rename(columns={'short_name': 'name'})
    if 'code' in result.columns:
        result['code'] = result['code'].astype(str).str.zfill(6)
    return result
```

### 3.4 优化映射效率

**现状**：`map(lambda x: mapping_cache.get(x, {}).get('industry_code', ''))` — 每行两次字典查找  
**优化**：预构建扁平映射字典

```python
# 构建扁平映射（O(n)预处理，后续O(1)查找）
code_to_industry = {k: v['industry_code'] for k, v in mapping_cache.items()}
code_to_indname  = {k: v['industry_name'] for k, v in mapping_cache.items()}

all_df['industry_code'] = all_df['code'].map(code_to_industry).fillna('')
all_df['industry_name'] = all_df['code'].map(code_to_indname).fillna('')
```

### 3.5 向量化结果构建

**现状**：`for rank, (_, row) in enumerate(top5.iterrows(), 1)` 逐行构建字典  
**优化**：

```python
top5 = good.nlargest(5, 'final_score').reset_index(drop=True)
top5['rank'] = range(1, len(top5) + 1)
top5['rq'] = date_str
top5['time'] = time_full

# 列重命名 + 选择
result_df = top5.rename(columns={'industry_code': 'code', 'industry_name': 'name'})
result_df = result_df[INDUSTRY_RESULT_COLUMNS]

# 数值精度
for col in ['avg_change_pct', 'avg_price', 'price_quality', 
            'raw_ratio', 'smooth_ratio', 'confidence', 'final_score']:
    result_df[col] = result_df[col].round(4)
result_df['count'] = result_df['count'].astype(int)
result_df['total'] = result_df['total'].astype(int)
```

### 3.6 精简日志

**现状**：6处debug日志在每次调用时输出  
**优化**：保留关键info日志，debug级别仅在首次映射或异常时输出

---

## 四、完整变更清单

### 4.1 文件变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `monitor_stock.py` | 修改 | 主函数优化 + 价格质量因子 |

### 4.2 新增模块级常量

```python
# 行业排行结果列
INDUSTRY_RESULT_COLUMNS = [
    'code', 'name', 'count', 'total', 'avg_change_pct', 'avg_price', 'price_quality',
    'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time'
]

# 价格质量因子默认参数
DEFAULT_PRICE_HALF_LIFE = 15.0  # A股中位价附近
DEFAULT_PRICE_WEIGHT = 0.5      # 温和影响
```

### 4.3 新增辅助函数

| 函数 | 说明 |
|------|------|
| `_ensure_industry_mapping(time_full)` | 确保行业映射缓存可用 |
| `_normalize_stock_df(df)` | 标准化列名和代码格式 |
| `_calc_price_quality(avg_price_series, K)` | 向量化计算价格质量因子 |

### 4.4 主函数 calculate_industry_topn 变更

| 步骤 | 现状 | 优化后 |
|------|------|--------|
| 空DataFrame返回 | 5处硬编码列名 | 统一使用 `INDUSTRY_RESULT_COLUMNS` |
| 缓存加载 | 25行嵌套if | 调用 `_ensure_industry_mapping()` |
| 列名标准化 | 重复代码×2 | 调用 `_normalize_stock_df()` |
| 行业映射 | lambda嵌套查找 | 扁平字典 + `Series.map(dict)` |
| groupby统计 | 只统计 change_pct均值和count | 新增 price均值 |
| 评分公式 | `smooth_ratio × confidence` | `smooth_ratio × confidence × price_quality^α` |
| 结果构建 | iterrows循环 | 向量化赋值 |
| 日志 | 6处debug | 精简为关键info |

### 4.5 调用方变更

**无需修改**。`industry_attack()` 调用 `calculate_industry_topn()` 的方式不变，新参数都有默认值。

---

## 五、评分对比示例

假设3个行业数据：

| 行业 | 上涨数 | 总数 | 行业均价 | 平均涨幅 |
|------|--------|------|---------|---------|
| A低价行业 | 20 | 50 | 3.2元 | 2.1% |
| B主流行业 | 12 | 30 | 28.5元 | 1.8% |
| C高价行业 | 8 | 25 | 55元 | 1.5% |

### 原评分（无价格因子）

| 行业 | smooth_ratio | confidence | final_score | 排名 |
|------|-------------|------------|-------------|------|
| A | (20+2)/(50+20)=0.314 | 0.838 | **0.264** | 1 |
| B | (12+2)/(30+20)=0.280 | 0.799 | **0.224** | 2 |
| C | (8+2)/(25+20)=0.222 | 0.781 | **0.174** | 3 |

### 新评分（α=0.5, K=15）

| 行业 | price_quality | factor(pq^0.5) | final_score | 排名 |
|------|--------------|-----------------|-------------|------|
| A | 0.596 | 0.772 | 0.264×0.772=**0.204** | **2** ↓ |
| B | 0.851 | 0.923 | 0.224×0.923=**0.207** | **1** ↑ |
| C | 0.964 | 0.982 | 0.174×0.982=**0.171** | 3 |

**效果**：均价3.2元的低价行业A从第1名降至第2名，均价28.5元的主流行业B晋升第1名。

---

## 六、回滚方案

设置 `price_weight=0` 即可完全关闭价格因子，退化为原始公式：

```python
# 关闭价格因子
hy_top5_df = calculate_industry_topn(top30_df, df_now, date_str, time_full, price_weight=0)
```

---

## 七、测试要点

1. **单元测试**：构造不同均价的mock数据，验证价格质量因子计算正确
2. **边界测试**：均价=0（除零保护）、均价极大值、price_weight=0（退化为原始）
3. **集成测试**：实盘运行观察TOP5排名变化，确认低价行业被合理降权
4. **性能测试**：对比优化前后耗时（预期持平或略优）
5. **下游兼容**：确认MySQL表自动新增 `avg_price`、`price_quality` 列
