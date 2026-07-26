# TickStateCache 通用类设计文档

**类名**: `TickStateCache`  
**位置**: `src/gs2026/monitor/tick_state_cache.py`  
**版本**: v1.0  
**状态**: ✅ 已实施  
**用途**: 所有"基于上一tick计算"的递推型指标的统一状态缓存

---

## 版本沿革

| 版本 | 时间 | 变更内容 | 状态 |
|------|------|----------|------|
| v1.0 | 2026-07-26 12:18 | 初始版：三级架构+算完存内存+修正错位bug，抽象为通用类 | ✅已实施 |

---

## 一、设计背景

### 1.1 适用场景

量化实时计算中，大量指标是**递推累积型**：

```
当前tick值 = f(上一tick值, 当前增量)
```

典型例子：

| 指标 | 递推公式 |
|------|----------|
| 累计主力净额 | `cum(T) = cum(T-1) + net(T)` |
| 峰值净额 | `peak(T) = max(peak(T-1), cum(T))` |
| 累计次数 | `count(T) = count(T-1) + has_net(T)` |

### 1.2 要解决的历史bug

旧实现（`monitor_stock._get_cached_prev_main`）存在两个严重问题：

**问题1：缺"算完存内存"步骤**
- 当前tick算完的`df_now`从未主动存入内存
- 内存里存的是"绕道Redis查来的上一tick数据"

**问题2：timestamp与data错位1个tick**
- 缓存语义：`{timestamp: T, data: T的上一tick数据}`
- 命中时返回落后2个tick的数据

**错位bug逐帧推演**（tick间隔15秒）：
```
T2(09:30:30) 要拿 T1(09:30:15) 数据
  查缓存: timestamp=09:30:15, 时间差15秒 → 命中！
  返回 cache['data'] = T0(09:30:00)  ❌ 落后2个tick
```

后果：累计净额继承错误tick，峰值净额计算偏差。

---

## 二、核心设计原则

| 原则 | 说明 |
|------|------|
| **语义清晰** | 内存缓存永远存"最近算完的那个tick"（timestamp与data一致，无错位） |
| **算完即存** | `put_current`在所有指标计算完成后调用 |
| **放宽命中** | 只要缓存是"当前时间之前的最近tick"（0<diff≤窗口）即命中 |
| **三级降级** | L1内存→L2Redis→L3MySQL，任何一级失败自动降级 |
| **不宕机必命中** | 只要上一tick执行了put_current，本tick get_prev必命中L1 |
| **兜底连续** | 三级全失败时用内存旧值兜底，保证累计不断裂 |

---

## 三、标准流程（四步）

```
每个tick的标准流程：
  ① get_prev()   拿上一tick（L1内存→L2Redis→L3MySQL）
  ② 计算          基于上一tick + 当前增量，计算当前tick所有指标
  ③ put_current() 【关键】算完所有指标后，把当前tick存入内存
  ④ 存表          异步存Redis/MySQL（供重启恢复）
       ↓
  下一tick的①直接命中L1内存
```

### 3.1 时序图（正常运行）

```
┌──────────────────────────────────────────────────────────┐
│  T1 tick                                                  │
│    ① get_prev(09:30:15) → L1命中 → 返回T0数据             │
│    ② df_now = calc(df_now, T0数据)                        │
│    ③ put_current(09:30:15, df_now)  ← 存T1入内存          │
│    ④ save_dataframe_async(df_now)                         │
├──────────────────────────────────────────────────────────┤
│  T2 tick                                                  │
│    ① get_prev(09:30:30) → L1命中 → 返回T1数据 ✓正确       │
│    ② df_now = calc(df_now, T1数据)                        │
│    ③ put_current(09:30:30, df_now)  ← 存T2入内存          │
│    ④ save_dataframe_async(df_now)                         │
└──────────────────────────────────────────────────────────┘
```

### 3.2 三级降级流程（重启后）

```
get_prev(current_time):
  L1内存? → 空（刚重启）
    ↓
  L2Redis: prev_time_finder找时间戳 → redis_loader加载
    ↓ 命中 → 返回
  L3MySQL: mysql_loader加载（Redis未命中时）
    ↓ 命中 → 返回
  兜底: 内存旧值（同日）→ 保证累计连续
    ↓ 无 → 返回None（走业务侧重启恢复）
```

---

## 四、API说明

### 4.1 构造函数

```python
TickStateCache(
    name: str,                          # 缓存名（日志区分）
    redis_loader: Callable,             # (table, time) -> data，Redis加载
    prev_time_finder: Callable,         # (table, current) -> prev_time，找上一tick时间戳
    mysql_loader: Callable = None,      # (table, time) -> data，MySQL兜底
    hit_window_seconds: int = 60,       # 内存命中容错窗口（秒）
    enable_debug_log: bool = False,     # 排查日志开关
)
```

### 4.2 核心方法

| 方法 | 说明 |
|------|------|
| `get_prev(table, current_time, date_str)` | 步骤①：三级降级获取上一tick |
| `put_current(table, current_time, date_str, data)` | 步骤③：算完存内存 |
| `invalidate()` | 清空内存（日期切换/重启） |
| `get_stats()` | 命中统计（l1_hit/l2_hit/l3_hit/miss/l1_rate） |

---

## 五、使用示例

### 5.1 初始化（延迟单例）

```python
_MAIN_NET_TICK_CACHE = None

def _get_main_net_tick_cache():
    global _MAIN_NET_TICK_CACHE
    if _MAIN_NET_TICK_CACHE is None:
        from gs2026.monitor.tick_state_cache import TickStateCache
        _MAIN_NET_TICK_CACHE = TickStateCache(
            name='main_net',
            redis_loader=lambda tbl, t: redis_util.load_dataframe_by_time(tbl, t),
            prev_time_finder=lambda tbl, t: redis_util.get_prev_timestamp_with_data(tbl, t),
            mysql_loader=_mysql_load,
            hit_window_seconds=60,
            enable_debug_log=True,  # 排查期开启
        )
    return _MAIN_NET_TICK_CACHE
```

### 5.2 主循环调用

```python
def deal_gp_works(loop_start):
    # ① 拿上一tick
    df_prev_main = _get_cached_prev_main(sssj_table, time_full, date_str)
    
    # ② 计算所有指标
    df_now = calculate_main_force_and_cumulative(df_now, df_prev_main, ...)
    # ... 其他指标计算 ...
    
    # ④ 存表
    save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
    
    # ③ 算完所有指标后，存内存（供下一tick）
    if not is_auction:
        _put_current_main_cache(df_now, time_full, date_str)
```

> ⚠️ 注意：步骤③在步骤④之后调用也可以，关键是**所有指标计算完成后**。

---

## 六、内存有效性判断（修正错位的核心）

```python
def _get_from_memory(self, current_time, date_str):
    c = self._mem
    if c['date'] != date_str or c['data'] is None:
        return None
    diff = (current_dt - cache_dt).total_seconds()
    # 放宽窗口：只要是"当前时间之前的最近tick"就命中
    if 0 < diff <= self._hit_window:  # 默认60秒
        return c['data']
    return None
```

**为什么无错位**：
- `put_current`存的是`{timestamp: 当前tick时间, data: 当前tick数据}`（一致）
- `get_prev`命中时，缓存的就是"上一个真实tick"，直接返回正确

---

## 七、验证结果

| 测试项 | 结果 |
|--------|------|
| T2正确返回T1（旧bug返回T0） | ✅ 通过 |
| 连续tick全部L1命中 | ✅ 3/3 |
| tick抖动（>20秒）仍命中内存 | ✅ 60秒窗口 |
| 重启后从Redis恢复 | ✅ 通过 |
| 首tick返回None | ✅ 通过 |

---

## 八、扩展新指标（未来）

任何"基于上一tick"的新指标，按以下步骤接入：

```python
# 1. 创建缓存实例
_NEW_CACHE = TickStateCache(
    name='new_indicator',
    redis_loader=...,
    prev_time_finder=...,
    mysql_loader=...,
)

# 2. 主循环三步
prev = _NEW_CACHE.get_prev(table, time, date)   # ①
result = compute(data, prev)                      # ②
_NEW_CACHE.put_current(table, time, date, result) # ③
```

---

## 九、排查日志清理

排查期 `enable_debug_log=True` 会输出：
- `[main_net][L1命中]` / `[L2命中]` / `[L3兜底]`
- `[存内存]` 当前tick已存入
- `[兜底]` / `[MISS]` 异常情况

**排查完成后**：将 `_get_main_net_tick_cache()` 中的 `enable_debug_log=True` 改为 `False`。

---

## 十、与其他缓存方案的关系

| 方案 | 适用场景 | 区别 |
|------|----------|------|
| **TickStateCache** | 递推累积（模式2） | 只需上一tick，算完存内存 |
| **snapshot_cache** | 全量累积/序列（模式1） | 需要全部过程数据，Snapshot |
| MySQL回填 | 滑动窗口（模式3） | 从表回填N条 |

详见 `多级缓存与中间状态统一存储方案.md` 第零章"累积模式分类与选型决策"。
