# monitor_stock.py Tick执行超3秒性能排查与优化方案

> **版本**: v1.0  
> **日期**: 2026-07-28  
> **状态**: 待审核  
> **问题**: monitor_stock.py 今日 Tick 总耗时常超 3 秒（tick间隔），例如 4534ms

---

## 一、问题现象

```
2026-07-28 09:37:49 [09:37:45] Tick总计: 4534.3ms
  | 采集949.5ms | 清洗34.9ms | 恢复200.5ms | 开盘146.6ms | 主力2179.6ms | 保存993.4ms
```

Tick 间隔应为 3000ms，实际 4534ms，**超时 1534ms**。两个大头：
- **主力 2179.6ms**（最大）
- **保存 993.4ms**（次大）
- 采集 949.5ms（网络，之前已做重试优化）

---

## 二、根因排查（逐阶段）

### 阶段耗时归属

| 阶段 | 耗时 | 主要操作 | 问题 |
|------|------|----------|------|
| 采集 | 949ms | 并发抓取5341只行情 | 网络耗时，漏采重试已优化，正常 |
| 清洗 | 35ms | 数据清洗 | 正常 |
| 恢复 | 200ms | df_prev恢复 | 正常 |
| 开盘 | 147ms | 开盘价计算 | 正常 |
| **主力** | **2179ms** | 主力净额+累计值计算 | **🔴 含新增Redis开销** |
| **保存** | **993ms** | top30计算+异步保存提交 | **🟡 top30计算+深拷贝** |

### 🔴 核心发现：净额为0修复引入的开销（主力阶段）

我之前为修复"净额为0/漏采"问题，在**主力阶段每tick新增了2个重操作**：

#### 问题1：`_load_peak_from_redis_hash`（第3145行，我新增）
```python
# 每tick执行：hgetall读取全部5341只股票的hash + Python循环解析
hist_peak = _load_peak_from_redis_hash(sssj_table)
raw = client.hgetall(hash_key)      # 读全部~5000条
for code_b, val_b in raw.items():   # Python循环5000次
    val.split(',')                   # 每条字符串分割
    peak_map[...] = float(parts[1])
```
- **开销**：hgetall传输5000条 + 5000次Python解析 + 后续 `.map()` 匹配
- **性质**：这是"第3层峰值保险"，**每tick都全量读取**，即使没有漏采

#### 问题2：`_save_cumulative_to_redis_hash`（第3160行，我新增）
```python
# 每tick执行：iterrows逐行遍历数千只股票（pandas反模式）
for _, row in df_write.iterrows():   # 🔴 逐行Python循环
    code = str(row['stock_code'])...
    mapping[code] = f"{cum},{max_cum},{count}"
client.hset(hash_key, mapping=mapping)
```
- **开销**：`iterrows()` 是 pandas 最慢的遍历方式，数千行每tick一次
- **性质**：写Redis hash供重启恢复，**每tick全量写**

**结论**：主力阶段2179ms中，**这两个新增操作估计占数百毫秒**（hgetall网络+双向5000次Python循环），是净额修复引入的**直接时效损耗**。

### 🟡 保存阶段993ms

- `culculate_gp_apqd_top30`（第3237行）：计算股票+行业top30、大盘强度，含多次 `save_dataframe_async` 和 `update_rank_redis`（主要耗时，但属原有逻辑）
- `save_dataframe_async` 内 `df.copy()`（深拷贝25列×5341行，主线程同步执行）
- 我新增的 `DERIVED_FIELDS` 补齐列（第3272行）：**开销极小**（仅列存在性检查+赋值，非瓶颈）

---

## 三、优化方案

### 🎯 方案A：优化净额修复引入的Redis开销（针对性，推荐，收益最大）

#### A-1：`_save_cumulative_to_redis_hash` 去掉iterrows（向量化）
```python
# 优化前：iterrows逐行（慢）
for _, row in df_write.iterrows():
    mapping[code] = f"{cum},{max_cum},{count}"

# 优化后：向量化构造（快10~50倍）
codes = df_write['stock_code'].astype(str).str.strip().str.zfill(6)
cum = df_write['cumulative_main_net'].fillna(0).astype(float)
max_cum = df_write['max_cumulative_main_net'].fillna(0).astype(float)
cnt = df_write['main_net_count'].fillna(0).astype(int)
vals = cum.astype(str) + ',' + max_cum.astype(str) + ',' + cnt.astype(str)
mapping = dict(zip(codes, vals))
client.hset(hash_key, mapping=mapping)
```
- **收益**：数千行 iterrows → 向量化，预计省 **100~300ms**

#### A-2：`_load_peak_from_redis_hash` 改为"仅漏采时才读"（按需加载）
```python
# 优化前：每tick无条件全量hgetall
hist_peak = _load_peak_from_redis_hash(sssj_table)

# 优化后：只在本tick确实有漏采股票时才读（漏采是小概率事件）
missing_codes = _get_missing_codes_this_tick()  # 采集阶段已知
if missing_codes:  # 仅漏采时才触发峰值兜底
    hist_peak = _load_peak_from_redis_hash(sssj_table)
    # ...只对漏采股票做峰值兜底
```
- **收益**：正常tick（无漏采）**完全跳过**hgetall+5000次解析，预计省 **200~400ms**
- **原理**：峰值兜底本就是为漏采设计的，无漏采时无需执行

#### A-3：`_save_cumulative_to_redis_hash` 异步化（可选）
- 与 `save_dataframe_async` 一样提交到线程池，不阻塞主tick
- **收益**：写Redis hash（数百ms）移出主线程，主tick立即返回

### 🎯 方案B：优化保存阶段（可选，收益中等）

#### B-1：`save_dataframe_async` 的 df.copy() 优化
- 当前深拷贝25列×5341行在主线程执行
- 可评估：是否能只拷贝需要的列，或用更轻量的隔离方式

#### B-2：`culculate_gp_apqd_top30` 内部审查
- 这是原有逻辑（非本次引入），如需进一步优化需单独深入
- 建议本次先不动，优先解决新增开销

### 🎯 方案C：将峰值兜底彻底移出主路径（治本，改动较大）

- 峰值保险、累计值持久化都属"容灾"逻辑，理论上都可异步
- 主tick只做核心计算，容灾写入全部异步化
- **收益最大但改动最大**，建议作为后续演进

---

## 四、我的倾向

| 方案 | 倾向 | 理由 |
|------|------|------|
| A-1 向量化save_hash | **必做** | iterrows是明确反模式，改动小、收益确定（省100~300ms）|
| A-2 峰值兜底按需加载 | **必做** | 正常tick跳过全量hgetall，省200~400ms，符合"漏采才兜底"的设计初衷 |
| A-3 save_hash异步化 | **建议做** | 进一步把Redis写移出主线程 |
| B-1 copy优化 | 可选 | 收益中等，需评估 |
| B-2/C | 暂不做 | 原有逻辑/改动大，本次聚焦新增开销 |

**推荐组合**：**A-1 + A-2 + A-3**（都针对我之前净额修复引入的开销），预计主力阶段从2179ms降至 **1300~1600ms**，Tick总计回到3秒内。

**关于"净额修复是否影响时效"的明确回答**：
> **是的，有影响。** 我之前为修复净额为0/漏采问题，在主力阶段每tick新增了 `_load_peak_from_redis_hash`（全量hgetall+5000次解析）和 `_save_cumulative_to_redis_hash`（iterrows逐行），这两个操作是本次超时的主要新增来源。方案A就是针对性消除这些开销，**在保留净额修复正确性的前提下恢复时效**。

---

## 五、实施步骤（审核通过后）

- [ ] A-1：`_save_cumulative_to_redis_hash` 改向量化构造mapping
- [ ] A-2：`_load_peak_from_redis_hash` 改为仅漏采时调用（需与采集阶段的漏采列表联动）
- [ ] A-3：`_save_cumulative_to_redis_hash` 提交到线程池异步执行
- [ ] 加细粒度计时日志（主力阶段内部分段计时，确认各操作实际耗时）
- [ ] 盘中验证：观察 Tick总计 是否回落到3秒内，净额/峰值数据仍正确

---

## 六、待确认点

```
【待确认1】是否认可"净额修复引入的Redis开销"为主要超时来源?
【待确认2】方案A(A-1向量化 + A-2按需加载 + A-3异步)是否实施?
【待确认3】A-2按需加载需要采集阶段提供"本tick漏采列表",是否已有该数据可复用?
          (漏采重试方案里的_fill_missing_stocks应已识别漏采股票)
【待确认4】是否需要先加细粒度计时日志,精确定位后再优化? (推荐:先加计时,数据驱动)
```

---

**待审核确认后实施。**
