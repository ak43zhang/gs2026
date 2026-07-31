# Redis优先方案设计

## 问题分析

当前Redis存储结构：
```
monitor_hy_top30_{date}:delta  → 只存最新tick的环比（覆盖）
```

问题：区间测算需要**历史所有tick**的环比数据，当前结构无法满足。

## 新方案：按tick存储历史数据

### Redis Key设计

```
# 每个tick的环比数据（hash）
monitor_hy_top30_{date}:delta:{time}  →  {industry_code: delta_pct}

# tick列表（供区间查询时遍历）
monitor_hy_top30_{date}:delta_times  →  [time1, time2, time3, ...] (list)

# 最新tick快速访问
monitor_hy_top30_{date}:delta:latest  →  {industry_code: delta_pct} (hash)
```

### 过期时间

全部设置为 **18小时 = 64800秒**

### 存储示例

```
monitor_hy_top30_20260729:delta:09:30:03  →  {881001: 0.0, 881002: 0.0, ...}
monitor_hy_top30_20260729:delta:09:30:06  →  {881001: 0.05, 881002: -0.02, ...}
monitor_hy_top30_20260729:delta:09:30:09  →  {881001: 0.03, 881002: 0.01, ...}
...
monitor_hy_top30_20260729:delta_times  →  ["09:30:03", "09:30:06", "09:30:09", ...]
monitor_hy_top30_20260729:delta:latest  →  {881001: 0.03, 881002: 0.01, ...}
```

## 改造点

### 1. monitor_stock.py - _save_industry_delta_to_redis

```python
def _save_industry_delta_to_redis(df: pd.DataFrame, date_str: str, time_full: str) -> None:
    """按tick存储历史环比数据，过期18小时"""
    try:
        client = redis_util._get_redis_client()
        
        # 1. 存该tick的环比数据（历史）
        hash_key = f"monitor_hy_top30_{date_str}:delta:{time_full}"
        mapping = dict(zip(
            df['code'].astype(str).str.strip(),
            df['delta_change_pct'].astype(float).astype(str)
        ))
        if mapping:
            client.hset(hash_key, mapping=mapping)
            client.expire(hash_key, 64800)  # 18小时
        
        # 2. 加入tick列表
        ts_list_key = f"monitor_hy_top30_{date_str}:delta_times"
        client.rpush(ts_list_key, time_full)
        client.expire(ts_list_key, 64800)
        
        # 3. 更新latest（快速访问）
        latest_key = f"monitor_hy_top30_{date_str}:delta:latest"
        client.hset(latest_key, mapping=mapping)
        client.expire(latest_key, 64800)
        
        # 4. 存绝对涨幅（供下一tick计算Δ）
        prev_key = f"monitor_hy_top30_{date_str}:prev_change"
        mapping_prev = dict(zip(
            df['code'].astype(str).str.strip(),
            df['avg_change_pct'].astype(float).astype(str)
        ))
        if mapping_prev:
            client.hset(prev_key, mapping=mapping_prev)
            client.expire(prev_key, 64800)
            
    except Exception as e:
        logger.warning(f"行业环比Redis缓存失败: {e}")
```

### 2. range_analysis_service.py - 优先Redis查询

```python
def query_range_industry(date: str, start_time: str, end_time: str, metric: str = 'change_pct'):
    if metric == 'delta_pct':
        # 优先从Redis查询
        result = _query_range_from_redis(date, start_time, end_time)
        if result['strongest_rank'] or result['weakest_rank']:
            return result
        # Redis无数据，降级到MySQL
        return _query_range_from_mysql(date, start_time, end_time, metric)

def _query_range_from_redis(date: str, start_time: str, end_time: str) -> dict:
    """从Redis读取区间内所有tick的环比数据"""
    try:
        client = redis_util._get_redis_client()
        
        # 获取tick列表
        ts_key = f"monitor_hy_top30_{date}:delta_times"
        all_times = client.lrange(ts_key, 0, -1)
        if not all_times:
            return empty
        
        # 筛选区间内tick
        times = [t.decode() if isinstance(t, bytes) else t for t in all_times]
        times = [t for t in times if start_time <= t <= end_time]
        
        # 读取每个tick的数据
        all_data = []
        for t in times:
            hash_key = f"monitor_hy_top30_{date}:delta:{t}"
            raw = client.hgetall(hash_key)
            if raw:
                for code_b, val_b in raw.items():
                    code = code_b.decode() if isinstance(code_b, bytes) else code_b
                    val = val_b.decode() if isinstance(val_b, bytes) else val_b
                    all_data.append({
                        'time': t, 'code': code, 
                        'delta_change_pct': float(val)
                    })
        
        # 转为DataFrame，按行业累计
        df = pd.DataFrame(all_data)
        # ... 累计计算逻辑 ...
        
    except Exception as e:
        logger.warning(f"Redis查询失败，降级到MySQL: {e}")
        return empty
```

### 3. 趋势图修复

当前趋势图从MySQL查，改为优先Redis：

```python
def get_industry_trend(date: str, code: str, start_time: str, end_time: str, metric: str = 'change_pct'):
    if metric == 'delta_pct':
        # 优先Redis
        trend = _get_trend_from_redis(date, code, start_time, end_time)
        if trend['times']:
            return trend
        # 降级MySQL
        return _get_trend_from_mysql(date, code, start_time, end_time, metric)

def _get_trend_from_redis(date: str, code: str, start_time: str, end_time: str) -> dict:
    """从Redis读取某行业区间趋势"""
    try:
        client = redis_util._get_redis_client()
        
        # 获取tick列表
        ts_key = f"monitor_hy_top30_{date}:delta_times"
        all_times = client.lrange(ts_key, 0, -1)
        times = [t.decode() if isinstance(t, bytes) else t for t in all_times]
        times = [t for t in times if start_time <= t <= end_time]
        
        # 读取每个tick的该行业数据
        values = []
        for t in times:
            hash_key = f"monitor_hy_top30_{date}:delta:{t}"
            val = client.hget(hash_key, code)
            if val:
                v = val.decode() if isinstance(val, bytes) else val
                values.append(float(v))
            else:
                values.append(0.0)
        
        return {'times': times, 'values': values, 'ranks': []}
    except:
        return {'times': [], 'values': [], 'ranks': []}
```

## 待确认

1. Redis 18小时过期时间是否满足？（覆盖交易日 09:30-15:00 + 盘后分析时间）
2. 是否需要在Redis存行业名称映射（code→name），避免查MySQL？
3. 历史数据（昨日及以前）是否只查MySQL（Redis已过期）？

审核通过后实施。
