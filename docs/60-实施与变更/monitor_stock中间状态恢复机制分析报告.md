# monitor_stock.py 中间状态恢复机制分析报告

**目标**: 用monitor_bond相同方法扫描monitor_stock.py，识别类似VWAP的累积型中间字段缺失恢复问题  
**扫描方法**: 模块级变量定义 + `+=`累积 + `global`声明 + 跨tick状态追踪  
**状态**: 🟡 待审核

---

## 一、核心结论（先给答案）

**monitor_stock.py 的中间状态恢复设计整体优于 monitor_bond.py！**

大部分累积/状态变量**已有恢复机制**，仅发现 **1个真实问题**（`_ever_zt_cache`）和 **1个轻微问题**（`_prev_tick_zt_codes`，但已被Redis兜底）。

| 变量 | 类型 | 恢复机制 | 风险 |
|------|------|----------|------|
| `cumulative_main_net` | 累计主力净额 | ✅ 每tick存MySQL，查上tick+当前 | 🟢无 |
| `_phase_history_map` | 大盘阶段滑动窗口 | ✅ MySQL回填159条 | 🟢无 |
| `_tick_window_cache` | 区间上攻次数 | ✅ `_batch_recover_window_counts` | 🟢无 |
| `_PREV_MAIN_CACHE` | 上tick数据缓存 | ✅ B+方案查MySQL | 🟢无 |
| `_prev_tick_zt_codes` | 上tick涨停集合 | ⚠️ 无，但Redis去重兜底 | 🟡轻微 |
| `_ever_zt_cache` | 当天曾涨停集合 | ❌ 无恢复 | 🔴中 |
| `_auction_data_fetched` | 竞价抓取标志 | 🟢 幂等，重启重抓无害 | 🟢无 |
| `_historical_stats_cache` | 疑似废弃 | - 仅定义未使用 | 🟢无 |

---

## 二、对比：为什么monitor_stock比monitor_bond好

### 2.1 累计主力净额 vs VWAP（关键对比）

这是最重要的发现——**同样是跨tick累积，两者设计截然不同**：

| 维度 | VWAP (monitor_bond) | cumulative_main_net (monitor_stock) |
|------|---------------------|-------------------------------------|
| 累积方式 | 内存变量 `_mkt_trend_vwap_sum_pv += ...` | DataFrame列 `cumulative_main_net` |
| 持久化 | ❌ 只存结果，中间值仅内存 | ✅ **每tick累计值都写入MySQL** |
| 下tick取值 | 从内存变量读 | **从MySQL查上一tick累计值** |
| 重启后 | ❌ 从0累积，计算错误 | ✅ **从MySQL自动恢复，计算正确** |

**cumulative_main_net的正确设计**（第540行）：
```python
def calculate_cumulative_main_net(df, table_name, current_time):
    # 从MySQL查询上一时刻的累计值
    query = f"""
        SELECT t1.stock_code, t1.cumulative_main_net
        FROM {table_name} t1
        INNER JOIN (SELECT stock_code, MAX(time) as max_time
                    FROM {table_name} WHERE time < '{current_time}' ...) t2 ...
    """
    prev_cumulative = pd.read_sql(query, con=engine)
    # 新累计值 = 上一时刻累计值(来自MySQL) + 当前值
    df['cumulative_main_net'] = df['cumulative_main_net_prev'] + df['main_net_amount']
```

**关键**：因为累计值随每个tick写入了sssj表，所以重启后能从MySQL查到，天然免疫宕机。这正是monitor_bond的VWAP应该学习的模式（但VWAP改用了Snapshot方案）。

### 2.2 大盘阶段 _phase_history_map（已有回填）

```python
# 第2529行：首次或跨表时从MySQL回填159条历史
if table_name not in _phase_history_map:
    _phase_history_map[table_name] = deque(maxlen=160)
    rows = conn.execute(f"SELECT body_up, body_down, min_up, min_down "
                        f"FROM `{table_name}` ORDER BY time DESC LIMIT 159")
    for row in rows:
        _phase_history_map[table_name].append(...)
```

**设计良好**：跟monitor_bond的形态历史类似，但它自己实现了MySQL回填，重启后自动恢复160点滑动窗口。

### 2.3 区间次数 _tick_window_cache（已有批量恢复）

```python
# 第3441行：宕机恢复
_batch_recover_window_counts(codes, date_str, time_full, table_name, engine)
```

---

## 三、发现的问题

### 🔴 问题1：`_ever_zt_cache`（当天曾涨停集合）无恢复

**位置**：第276行定义，第1260-1289行使用

**代码**：
```python
_ever_zt_cache: Set[str] = set()   # 当天曾涨停的股票代码
_ever_zt_cache_date: str = ""

def is_ever_zt(code, date_str) -> int:
    if date_str != _ever_zt_cache_date:
        _ever_zt_cache.clear()   # 日期切换清空
        _ever_zt_cache_date = date_str
    return 1 if code in _ever_zt_cache else 0
```

**问题**：
- 该集合记录"当天曾经涨停过的股票"
- 重启后为空 → `is_ever_zt` 全部返回0
- 直到这些股票**再次涨停**才会重新加入
- 若某股9:35涨停后回封，14:00重启 → 该股`is_ever_zt`错误返回0

**影响**：`ever_zt`字段用于判断"打板回封"等策略，重启后当天早盘涨停记录丢失，影响选股准确性。

**风险等级**：🔴 中（影响选股字段，但非致命）

### 🟡 问题2：`_prev_tick_zt_codes`（上tick涨停集合）无恢复，但已被Redis兜底

**位置**：第300行定义，第1334-1343行使用

**代码**：
```python
_prev_tick_zt_codes: Set[str] = set()

def _detect_anomaly_zt(zt_codes, df_now, date_str, time_full):
    # 增量涨停 = 当前涨停 - 上一tick涨停
    new_zt_codes = zt_codes - _prev_tick_zt_codes
    _prev_tick_zt_codes = zt_codes.copy()
    ...
    for code in new_zt_codes:
        # Redis 原子去重（关键兜底！）
        if redis_client.sadd(redis_key, member) != 1:
            continue  # 已记录过，跳过
```

**问题**：
- 重启后`_prev_tick_zt_codes`为空
- 重启后第一个tick，所有涨停都被当作"新涨停"
- 触发大量异动检测

**但已被兜底**：Redis `SADD anomaly:{date}` 原子去重，已记录的涨停会被跳过，**不会重复写异动表**。

**风险等级**：🟡 轻微（仅重启后1个tick多做无效计算，Redis去重保证不误报）

---

## 四、修复方案

### 4.1 问题1修复：`_ever_zt_cache` 从MySQL恢复

**方案**：借鉴`_phase_history_map`的MySQL回填模式，首次调用时从sssj表恢复当天曾涨停的股票。

**关键**：sssj表已持久化 `is_zt` 列（第2880行 `calc_is_zt_vectorized` 计算后随df存入），
直接查 `is_zt=1` 即可，比 `change_pct>=9.9` 准确（正确处理ST股5%、科创板20%涨停幅度）。

```python
_ever_zt_recovered_date = ""  # 恢复标志

def _recover_ever_zt(date_str, table_name, engine):
    """从MySQL恢复当天曾涨停的股票集合（查is_zt=1）"""
    global _ever_zt_cache, _ever_zt_recovered_date
    if _ever_zt_recovered_date == date_str:
        return  # 已恢复
    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            # 表可能不存在（早盘首tick），先检查
            exists = conn.execute(sa_text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=:t"
            ), {'t': table_name}).fetchone()
            if exists:
                # 查询当天所有曾涨停的股票（is_zt=1，已由calc_is_zt_vectorized正确判定）
                rows = conn.execute(sa_text(
                    f"SELECT DISTINCT stock_code FROM `{table_name}` WHERE is_zt = 1"
                )).fetchall()
                for row in rows:
                    _ever_zt_cache.add(str(row[0]))
                logger.info(f"[恢复] ever_zt从MySQL恢复 {len(_ever_zt_cache)} 只曾涨停股票")
        _ever_zt_recovered_date = date_str
    except Exception as e:
        logger.warning(f"[恢复] ever_zt恢复失败(降级): {e}")

# 在 update_ever_zt_cache 首次调用时触发恢复（该函数每tick调用，能拿到date_str）
def update_ever_zt_cache(date_str, zt_codes, table_name=None, engine=None):
    global _ever_zt_cache, _ever_zt_cache_date
    if date_str != _ever_zt_cache_date:
        _ever_zt_cache.clear()
        _ever_zt_cache_date = date_str
        # 【新增】跨日/重启后尝试从MySQL恢复
        if table_name and engine:
            _recover_ever_zt(date_str, table_name, engine)
    _ever_zt_cache.update(zt_codes)
```

**接入点**（第2893行）：
```python
# 修改前
update_ever_zt_cache(date_str, zt_codes)
# 修改后（传入表名和engine以支持恢复）
update_ever_zt_cache(date_str, zt_codes, table_name=sssj_table, engine=engine)
```

### 4.2 问题2修复：`_prev_tick_zt_codes`（可选，优先级低）

**方案A（推荐）**：不修复。Redis去重已保证正确性，仅重启后1tick的性能损耗可忽略。

**方案B（如需彻底）**：重启后从Redis已记录的涨停集合恢复：
```python
def _recover_prev_tick_zt(date_str):
    global _prev_tick_zt_codes
    trading_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    redis_key = f"anomaly:{trading_date}"
    members = redis_client.smembers(redis_key)
    _prev_tick_zt_codes = {m.decode().split(':')[0] for m in members}
```

---

## 五、是否需要纳入Snapshot方案？

**结论：不需要。**

| 变量 | 是否纳入Snapshot | 理由 |
|------|------------------|------|
| `_ever_zt_cache` | ❌ 不需要 | 直接从sssj表查change_pct即可恢复，无需快照 |
| `_prev_tick_zt_codes` | ❌ 不需要 | Redis去重已兜底 |
| 其他 | ❌ 不需要 | 已有各自的MySQL恢复机制 |

**原因**：monitor_stock的累积字段（cumulative_main_net）本身就持久化到MySQL，滑动窗口（phase/window_count）也有专门回填函数。只有`_ever_zt_cache`缺恢复，而它可以直接从现有sssj表数据反推（查当天change_pct>=9.9的股票），不需要额外的Snapshot存储。

---

## 六、待审核确认

```
□ 核心结论：monitor_stock恢复设计整体优于monitor_bond
□ 关键对比：cumulative_main_net每tick存MySQL（正确），VWAP只存内存（错误）
□ 问题1：_ever_zt_cache无恢复（🔴中风险），影响曾涨停判断
□ 问题2：_prev_tick_zt_codes无恢复（🟡轻微），但Redis去重已兜底
□ 修复方案1：_ever_zt_cache从MySQL查change_pct>=9.9恢复
□ 修复方案2：_prev_tick_zt_codes可不修复（Redis兜底）
□ 不需要Snapshot方案：现有MySQL数据可反推恢复

请审核，确认：
1. 是否修复 `_ever_zt_cache`（问题1）？→ 推荐修复，用 `WHERE is_zt=1` 从sssj表恢复（字段已确认存在）
2. `_prev_tick_zt_codes` 是否需要修复（问题2）？→ 推荐不修复（Redis去重已兜底）
```

