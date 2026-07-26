# 基于上一tick计算的标准设计模式 + 内存缓存写入机制分析

**目标**: 1)确定当前tick如何存入内存供下一tick使用；2)制定"基于上一tick计算"的统一设计模式  
**状态**: ✅ 已实施（通用类见 `TickStateCache通用类设计文档.md`）

> 实施成果：
> - 抽象通用类 `TickStateCache`（`src/gs2026/monitor/tick_state_cache.py`）
> - 修正错位bug（T2不再返回T0，验证通过）
> - 补上"算完存内存"步骤③
> - 放宽内存命中窗口至60秒
> - 加排查日志（`enable_debug_log=True`，排查后统一关闭）

---

## 一、问题2答案：当前tick如何存入内存？

### 1.1 关键发现（核心缺陷）

**当前tick计算完的 `df_now` 从未主动存入内存缓存！**

搜索证据：
- `_PREV_MAIN_CACHE` 只有3个写入点：定义(286)、Redis加载后(400)、失效清空(413)
- **没有任何地方把当前tick算完的 `df_now` 存入缓存**

### 1.2 当前内存缓存的实际写入逻辑

```python
def _get_cached_prev_main(sssj_table, current_time, date_str):
    # ① 先查内存缓存
    if 缓存有效 and 10 <= time_diff <= 20:
        return cache['data'].copy()   # 命中
    
    # ② 缓存失效 → 从Redis加载"上一tick"
    prev_time = get_prev_timestamp_with_data(sssj_table, current_time)
    df_prev_main = load_dataframe_by_time(sssj_table, prev_time)
    
    # ③ 【关键】把"从Redis加载的上一tick"存入缓存
    if df_prev_main is not None:
        _PREV_MAIN_CACHE = {
            'timestamp': current_time,    # ← 注意：存的是current_time
            'data': df_prev_main.copy(),  # ← 存的是"上一tick"数据
        }
    return df_prev_main
```

### 1.3 这个逻辑的问题

**内存缓存存的不是"当前tick"，而是"上一tick从Redis查到的数据"，且timestamp标记为current_time。**

缓存语义：`{timestamp: T, data: T的上一tick数据}`（标签与内容错位1个tick）

**逐帧推演（已验证，tick间隔15秒）**：

```
T1(09:30:15) 调用 get_prev(current=09:30:15)，目的拿T0数据：
  查缓存 → 空 → 查Redis: prev_time=09:30:00 → load → T0数据
  写缓存: {timestamp: 09:30:15, data: T0数据}   ← 标签T1，内容T0
  返回 T0 ✓ 正确

T2(09:30:30) 调用 get_prev(current=09:30:30)，目的拿T1数据：
  查缓存: timestamp=09:30:15, time_diff=15秒, 10<=15<=20 ✓命中
  返回 cache['data'] = T0数据（09:30:00）
  ❌❌❌ 错误！T2需要T1数据，却返回了T0数据（落后2个tick）
```

**已确认的严重bug**：

| 风险 | 说明 | 严重度 |
|------|------|--------|
| 🔴 **风险3：缓存命中返回落后2个tick的数据** | 缓存data存的是"timestamp的上一tick"，命中时timestamp又恰是上一tick，导致返回数据比current落后2个tick | 🔴🔴🔴 严重 |

**对累计净额的影响**（`_carry_forward_cumulative_fields`从df_prev_main继承累计值）：
- 缓存命中时，继承的是T0的累计值而非T1 → **累计值来源错误**
- 增量计算基准错误（用T0而非T1算价差/量差）
- 结果：**累计净额可能少加一个tick的增量，或峰值净额计算偏差**

> ⚠️ 这解释了你观察到的"峰值净额有值但过程中丢失上一tick"——缓存命中时用了错误的旧tick数据。

> 📌 但由于影响生产交易，建议**先加日志实测确认**，再实施修复。

---

## 二、你期望的正确设计模式

### 2.1 标准模式：算完即存内存

```
每个tick的标准流程：
  ① 从内存拿上一tick的值（L1，不宕机时必有）
  ② 基于上一tick + 当前增量，计算当前tick
  ③ 【关键】算完后，立即把当前tick存入内存
  ④ 同时异步存Redis/MySQL（供重启恢复）
     ↓
  下一tick的①直接命中内存
```

### 2.2 为什么"不宕机时先查内存肯定有值"

你的推理是对的，但**前提是必须有步骤③**。当前代码缺步骤③，所以内存里存的是"绕道Redis查来的上一tick"，而非"上一tick算完直接存的"。

**修正后**：只要上一tick执行了步骤③，本tick步骤①就必然命中内存（除非宕机重启）。

---

## 三、统一设计模式（问题1：以后所有基于tick的计算都遵循）

### 3.1 通用模式定义：`TickStateCache`

```python
class TickStateCache:
    """
    基于上一tick计算的通用状态缓存
    
    适用：所有"当前tick = f(上一tick, 当前增量)"的递推计算
    如：累计主力净额、峰值净额、累计次数等
    
    三级架构：L1内存 → L2Redis → L3MySQL
    核心原则：算完即存内存（步骤③），保证下一tick命中
    """
    
    def get_prev(self, key, current_time, date_str):
        """① 获取上一tick的值（三级降级）"""
        # L1: 内存（不宕机时必有）
        if self._mem_valid(key, current_time, date_str):
            return self._mem[key]['data']
        # L2: Redis
        data = self._load_redis(key, current_time)
        if data is not None:
            return data
        # L3: MySQL
        return self._load_mysql(key, current_time)
    
    def put_current(self, key, current_time, date_str, data):
        """③ 算完后存入内存（关键步骤，供下一tick用）"""
        self._mem[key] = {
            'date': date_str,
            'timestamp': current_time,  # ← 存当前tick时间
            'data': data.copy(),        # ← 存当前tick数据
        }
        # 异步存Redis/MySQL（供重启恢复）
        self._async_save(key, current_time, data)
    
    def _mem_valid(self, key, current_time, date_str):
        """内存有效性：同日 + 是最近的tick（放宽时间窗口）"""
        c = self._mem.get(key)
        if not c or c['date'] != date_str:
            return False
        # 只要缓存时间 < 当前时间且在合理范围（放宽到60秒容错）
        diff = self._time_diff(current_time, c['timestamp'])
        return 0 < diff <= 60
```

### 3.2 标准调用流程

```python
def deal_tick(loop_start):
    # ① 拿上一tick
    df_prev = state_cache.get_prev('main_net', time_full, date_str)
    
    # ② 计算当前tick
    df_now = calculate_cumulative(df_now, df_prev)
    
    # ③ 【关键】算完立即存内存（供下一tick）
    state_cache.put_current('main_net', time_full, date_str, df_now)
    
    # ④ 存sssj表（Redis/MySQL已在put_current异步完成）
    save_dataframe_async(df_now, sssj_table, ...)
```

---

## 四、修复方案（针对现有累计净额）

### 4.1 核心修复：增加步骤③（算完存内存）

**位置**：主力净额计算完成后（第3021行 `_save_cumulative_to_redis_hash` 附近）

```python
# 现状：算完只存了Redis hash，没存内存缓存
_save_cumulative_to_redis_hash(df_now, sssj_table)

# 【新增】算完后把当前tick存入内存缓存（供下一tick直接命中）
_update_prev_main_cache(df_now, time_full, date_str)
```

```python
def _update_prev_main_cache(df_now, current_time, date_str):
    """算完当前tick后，存入内存供下一tick使用（步骤③）"""
    global _PREV_MAIN_CACHE
    _PREV_MAIN_CACHE = {
        'date': date_str,
        'timestamp': current_time,   # 当前tick时间
        'data': df_now.copy(),       # 当前tick完整数据
        'hit_count': 0
    }
```

### 4.2 配合修复：get时优先用内存（放宽窗口）

```python
def _get_cached_prev_main(sssj_table, current_time, date_str):
    cache = _PREV_MAIN_CACHE
    if (cache['date'] == date_str and cache['data'] is not None):
        diff = time_diff(current_time, cache['timestamp'])
        # 放宽：只要是最近的上一个tick（0~60秒），就命中
        if 0 < diff <= 60:
            cache['hit_count'] += 1
            return cache['data'].copy()
    # 失效才走Redis→MySQL（重启后首tick）
    ...
```

### 4.3 修复后的效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 正常运行 | 每tick查Redis（缓存逻辑有误） | ✅ L1内存命中，0查询 |
| tick抖动(>20秒) | ❌ 缓存失效→查Redis | ✅ 60秒内仍命中内存 |
| 重启后首tick | Redis hash/MySQL恢复 | ✅ 不变（三级恢复保留） |
| 数据连续性 | 可能断裂 | ✅ 内存保证连续 |

---

## 五、待审核确认

```
□ 问题2答案：当前tick的df_now从未主动存入内存（缺步骤③）
□ 现状缺陷：内存缓存存的是"绕道Redis查的上一tick"，非"算完直接存"
□ 风险3：缓存命中逻辑可能返回错误的tick数据（需实测验证）
□ 统一模式：TickStateCache（get_prev三级 + put_current算完存内存）
□ 修复1：主力净额算完后增加_update_prev_main_cache（步骤③）
□ 修复2：get时放宽内存命中窗口(0~60秒)
□ 修复3：保留现有三级重启恢复不变
□ 设计原则：以后所有"基于上一tick"计算都用此模式

请审核：
1. 是否确认"缺步骤③"是根本原因？（我可加日志实测验证）
2. 是否按此方案修复（算完存内存 + 放宽窗口）？
3. 是否将TickStateCache抽象为通用模式，用于未来所有递推计算？
```

