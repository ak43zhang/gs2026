# monitor_stock性能优化方案A - 代码级实施细节

> **版本**: v1.0  
> **日期**: 2026-07-28  
> **状态**: 待审核后实施  
> **目标**: 主力阶段 2179ms → 1300~1600ms，Tick总计回到3秒内

---

## 一、A-1: `_save_cumulative_to_redis_hash` 向量化改造

### 当前代码（慢）
```python
# 行1048-1054: iterrows逐行遍历（pandas反模式）
mapping = {}
for _, row in df_write.iterrows():  # 🔴 慢：Python循环数千次
    code = str(row['stock_code']).strip().zfill(6)
    cum = float(row.get('cumulative_main_net', 0))
    max_cum = float(row.get('max_cumulative_main_net', 0))
    count = int(row.get('main_net_count', 0))
    mapping[code] = f"{cum},{max_cum},{count}"
```

### 优化后代码（快10~50倍）
```python
# 向量化构造mapping（无Python循环）
codes = df_write['stock_code'].astype(str).str.strip().str.zfill(6)
cum = df_write['cumulative_main_net'].fillna(0).astype(float)
max_cum = df_write['max_cumulative_main_net'].fillna(0).astype(float)
count = df_write['main_net_count'].fillna(0).astype(int)

# 向量化字符串拼接（比逐行快得多）
vals = cum.astype(str) + ',' + max_cum.astype(str) + ',' + count.astype(str)
mapping = dict(zip(codes, vals))
```

### 完整替换函数
```python
def _save_cumulative_to_redis_hash(df_now: pd.DataFrame, sssj_table: str) -> None:
    """将当前累计值写入Redis hash（向量化优化版）"""
    try:
        client = redis_util._get_redis_client()
        hash_key = f"{sssj_table}:cumulative"
        
        # 只写入有非零累计值的股票
        mask = (df_now['cumulative_main_net'] != 0) | \
               (df_now['max_cumulative_main_net'] != 0) | \
               (df_now['main_net_count'] != 0)
        df_write = df_now[mask]
        
        if df_write.empty:
            return
        
        # 【A-1优化】向量化构造mapping（替代iterrows）
        codes = df_write['stock_code'].astype(str).str.strip().str.zfill(6)
        cum = df_write['cumulative_main_net'].fillna(0).astype(float)
        max_cum = df_write['max_cumulative_main_net'].fillna(0).astype(float)
        count = df_write['main_net_count'].fillna(0).astype(int)
        
        # 向量化字符串拼接
        vals = cum.astype(str) + ',' + max_cum.astype(str) + ',' + count.astype(str)
        mapping = dict(zip(codes, vals))
        
        if mapping:
            client.hset(hash_key, mapping=mapping)
            client.expire(hash_key, 86400)
            
    except Exception as e:
        logger.warning(f"写入Redis累计值hash失败（非关键）: {e}")
```

---

## 二、A-2: `_load_peak_from_redis_hash` 按需加载改造

### 设计思路
峰值兜底本就是为**漏采股票**设计的，正常tick（无漏采）无需执行全量hgetall。

### 实现方案
在采集阶段（`_fill_missing_stocks`）识别漏采股票，主力阶段只对这些股票做峰值兜底。

### 步骤1: 采集阶段记录漏采列表（全局变量）
```python
# 文件顶部添加全局变量（行~100附近，与其他全局变量一起）
_missing_codes_this_tick: Set[str] = set()  # 本tick漏采的股票代码

# 修改 _fill_missing_stocks 函数（行2896附近）
def _fill_missing_stocks(df_now, df_prev, time_full):
    """【漏采兜底·第2层】补齐完全缺失的股票"""
    global _missing_codes_this_tick
    
    if df_prev is None or df_prev.empty or df_now is None or df_now.empty:
        _missing_codes_this_tick = set()  # 清空
        return df_now, 0
    
    try:
        now_codes = set(df_now['stock_code'].astype(str).str.strip().str.zfill(6))
        prev_codes = set(df_prev['stock_code'].astype(str).str.strip().str.zfill(6))
        missing = prev_codes - now_codes
        
        # 【A-2关键】记录本tick漏采股票，供峰值兜底按需使用
        _missing_codes_this_tick = missing.copy()
        
        if not missing:
            return df_now, 0
        
        # ...原有补齐逻辑不变...
        
    except Exception as e:
        _missing_codes_this_tick = set()  # 异常时清空
        logger.error(f"[{time_full}] 补齐漏采股票失败(降级): {e}")
        return df_now, 0
```

### 步骤2: 峰值兜底改为按需（行3145附近）
```python
# 【A-2优化】峰值兜底改为仅漏采股票才执行
if not is_auction and df_prev_main is not None and not df_prev_main.empty:
    try:
        # 原代码：无条件全量读取
        # hist_peak = _load_peak_from_redis_hash(sssj_table)  # 🔴 慢：每tick全量hgetall
        
        # 【A-2优化】仅当本tick有漏采时才读取峰值兜底
        global _missing_codes_this_tick
        hist_peak = None
        if _missing_codes_this_tick:  # 有漏采才执行
            # 只读取漏采股票的峰值（而非全量5000只）
            hist_peak = _load_peak_for_codes(sssj_table, _missing_codes_this_tick)
        
        if hist_peak:
            # 只对漏采股票做峰值兜底
            for code in _missing_codes_this_tick:
                if code in hist_peak:
                    # 找到对应行并兜底
                    mask = df_now['stock_code'].astype(str).str.strip().str.zfill(6) == code
                    if mask.any():
                        df_now.loc[mask, 'max_cumulative_main_net'] = max(
                            df_now.loc[mask, 'max_cumulative_main_net'].fillna(0).iloc[0],
                            hist_peak[code]
                        )
        
        # 清空本tick记录（已使用）
        _missing_codes_this_tick = set()
        
    except Exception as _e:
        logger.warning(f"[{time_full}] 峰值兜底失败(非关键): {_e}")
```

### 步骤3: 新增按需读取函数（行~1108附近）
```python
def _load_peak_for_codes(sssj_table: str, codes: Set[str]) -> Dict[str, float]:
    """
    【A-2优化】只读取指定股票代码的峰值（而非全量hgetall）
    
    使用 hmget 替代 hgetall，只取需要的字段，网络传输量大幅减少
    """
    if not codes:
        return {}
    
    try:
        client = redis_util._get_redis_client()
        hash_key = f"{sssj_table}:cumulative"
        
        # 使用 hmget 只读取指定codes（而非hgetall全量）
        code_list = list(codes)
        raw_values = client.hmget(hash_key, code_list)
        
        peak_map = {}
        for code, val in zip(code_list, raw_values):
            if val is None:
                continue
            val_str = val.decode() if isinstance(val, bytes) else val
            parts = val_str.split(',')
            if len(parts) == 3:
                peak_map[str(code).strip().zfill(6)] = float(parts[1])  # max_cum
        
        return peak_map
        
    except Exception as e:
        logger.warning(f"读取Redis峰值(按需)失败(非关键): {e}")
        return {}

# 保留原函数供其他场景使用（如重启恢复）
def _load_peak_from_redis_hash(sssj_table: str) -> Dict[str, float]:
    """【保留】全量读取峰值（供重启恢复等场景）"""
    # ...原实现不变...
```

---

## 三、A-3: `_save_cumulative_to_redis_hash` 异步化

### 方案
将Redis写入提交到线程池，不阻塞主tick。

### 实现
```python
# 文件顶部导入（已有 _mysql_executor, _redis_executor 等线程池）
from concurrent.futures import ThreadPoolExecutor

# 复用已有的 _redis_executor（与 save_dataframe_async 共用）
# 或新增专用executor（如果担心竞争）

# 修改调用点（行3160附近）
# 原代码（同步）:
# _save_cumulative_to_redis_hash(df_now, sssj_table)

# 【A-3优化】异步提交
_redis_executor.submit(_save_cumulative_to_redis_hash, df_now.copy(), sssj_table)
# 注意：df_now.copy() 避免异步线程与主线程并发修改
```

### 完整修改（行3155-3165附近）
```python
# 【漏采保险·第3层-峰值单调兜底】用Redis历史峰值兜底
# 【A-2优化】改为按需加载（见上文）
# ...

# 【A-3优化】累计值写入Redis改为异步
# 原代码: _save_cumulative_to_redis_hash(df_now, sssj_table)
_redis_executor.submit(_save_cumulative_to_redis_hash, 
                       df_now[['stock_code', 'cumulative_main_net', 
                               'max_cumulative_main_net', 'main_net_count']].copy(), 
                       sssj_table)
# 只copy需要的列，减少序列化开销
```

---

## 四、细粒度计时日志（验证用）

### 在主力阶段内部分段计时
```python
# 行3035附近，t5开始处
t5 = time.time()
t5_sub = {}  # 子阶段计时

if not df_now.empty:
    # 子阶段1: 涨停计算
    t5_1 = time.time()
    # ...涨停计算...
    t5_sub['zt'] = (time.time() - t5_1) * 1000
    
    # 子阶段2: 获取df_prev_main（含缓存）
    t5_2 = time.time()
    df_prev_main = _get_cached_prev_main(...)
    t5_sub['prev'] = (time.time() - t5_2) * 1000
    
    # 子阶段3: 峰值兜底（A-2优化点）
    t5_3 = time.time()
    # ...峰值兜底...
    t5_sub['peak'] = (time.time() - t5_3) * 1000
    
    # 子阶段4: 主力净额计算
    t5_4 = time.time()
    # ...calculate_main_force...
    t5_sub['calc'] = (time.time() - t5_4) * 1000
    
    # 子阶段5: 保存hash（A-1/A-3优化点）
    t5_5 = time.time()
    # ..._save_cumulative_to_redis_hash...
    t5_sub['save_hash'] = (time.time() - t5_5) * 1000

# 输出子阶段耗时
if t5_sub:
    logger.info(f"[主力阶段细分] zt={t5_sub.get('zt',0):.1f}ms | "
                f"prev={t5_sub.get('prev',0):.1f}ms | "
                f"peak={t5_sub.get('peak',0):.1f}ms | "
                f"calc={t5_sub.get('calc',0):.1f}ms | "
                f"save_hash={t5_sub.get('save_hash',0):.1f}ms")

t5_elapsed = (time.time() - t5) * 1000
```

---

## 五、实施检查清单

- [ ] **A-1**: 替换 `_save_cumulative_to_redis_hash` 为向量化版本
- [ ] **A-2**: 添加 `_missing_codes_this_tick` 全局变量
- [ ] **A-2**: 修改 `_fill_missing_stocks` 记录漏采列表
- [ ] **A-2**: 添加 `_load_peak_for_codes` 按需读取函数
- [ ] **A-2**: 修改峰值兜底调用点为按需版本
- [ ] **A-3**: 修改 `_save_cumulative_to_redis_hash` 调用为异步提交
- [ ] **验证**: 盘中观察日志，确认子阶段耗时下降
- [ ] **验证**: 确认净额/峰值数据仍正确（无回归）

---

## 六、预期收益

| 优化 | 原耗时 | 优化后 | 收益 |
|------|--------|--------|------|
| A-1 iterrows→向量化 | ~200-400ms | ~10-30ms | **省150~350ms** |
| A-2 hgetall全量→hmget按需 | ~150-300ms(有漏采时) | ~0ms(无漏采) | **省150~300ms(常态)** |
| A-3 同步→异步 | ~50-100ms(阻塞) | ~5ms(提交) | **省50~100ms** |
| **合计** | **~400-800ms** | **~15-35ms** | **省400~750ms** |

主力阶段: 2179ms → **1400~1800ms** (中位432ms不变，尖峰降低)
Tick总计: 4534ms → **<3000ms** (回到3秒内)

---

**待审核确认后实施。**
