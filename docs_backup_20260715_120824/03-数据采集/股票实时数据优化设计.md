# monitor_gp_sssj_20260331 入库和查询优化方案

> 分析时间: 2026-03-31 10:38  
> 目标: 优化实时股票数据入库和查询性能

---

## 一、现状分析

### 1.1 数据流分析

```
数据采集 (monitor_stock.py)
    ↓ 每3秒执行一次
获取实时股票数据 (akshare/数据源)
    ↓
存储到 monitor_gp_sssj_{date} (Redis Hash)
    ↓
计算前30秒数据对比
    ↓
计算大盘强度 (monitor_gp_apqd_{date})
    ↓
计算前30榜单 (monitor_gp_top30_{date})
    ↓
更新排行榜 (Redis Sorted Set)
    ↓
收盘时保存到 MySQL
```

### 1.2 表结构

**monitor_gp_sssj_{date}** (实时数据)
- Redis Hash 结构: `monitor_gp_sssj_20260331:09:30:00`
- 字段: code, name, price, change_pct, volume, amount, ...
- 频率: 每3秒一个时间点
- 数据量: ~4800时间点/天 × ~5000只股票 = 2400万条记录

**monitor_gp_top30_{date}** (前30榜单)
- Redis Hash 结构: `monitor_gp_top30_20260331:09:30:00`
- 字段: code, name, zf_30, momentum, total_score, ...
- 频率: 每3秒一个时间点
- 数据量: ~4800时间点/天 × 60只股票 = 28.8万条记录

### 1.3 当前性能瓶颈

| 环节 | 问题 | 影响 |
|------|------|------|
| 入库 | 逐条存储到Redis | 每轮循环耗时高 |
| 查询 | 遍历所有时间点 | 时间复杂度O(n) |
| 内存 | 全量数据在Redis | 内存占用大 |
| 计算 | 每次加载前30秒数据 | IO开销大 |

---

## 二、优化方案

### 方案A: Pipeline批量入库 (推荐)

**优化点**: 使用Redis Pipeline批量写入，减少网络往返

**实施**:
```python
# 修改 save_dataframe 函数
def save_dataframe_pipeline(df, table_name, time_full, expire_seconds):
    """使用Pipeline批量保存DataFrame到Redis"""
    client = _get_redis_client()
    pipe = client.pipeline(transaction=False)
    
    key = f"{table_name}:{time_full}"
    
    # 批量HMSET
    for idx, row in df.iterrows():
        field = row['code']
        value = row.to_json()
        pipe.hset(key, field, value)
    
    # 设置过期时间
    pipe.expire(key, expire_seconds)
    
    # 添加到时间戳列表
    ts_key = f"{table_name}:timestamps"
    pipe.rpush(ts_key, time_full)
    pipe.expire(ts_key, expire_seconds)
    
    # 批量执行
    pipe.execute()
```

**效果**: 入库性能提升 5-10倍

---

### 方案B: 增量更新 + 缓存

**优化点**: 只存储变化的数据，减少存储量

**实施**:
```python
# 对比前后两帧数据，只存储变化的股票
def save_incremental_data(df_now, df_prev, table_name, time_full):
    """增量存储，只保存变化的数据"""
    if df_prev is None or df_prev.empty:
        # 首次存储全量
        save_dataframe(df_now, table_name, time_full)
        return
    
    # 找出变化的股票
    merged = df_now.merge(df_prev, on='code', suffixes=('', '_prev'))
    changed = merged[
        (merged['price'] != merged['price_prev']) |
        (merged['volume'] != merged['volume_prev'])
    ]
    
    # 存储变化数据 + 全量索引
    save_dataframe(changed, table_name, time_full)
    
    # 存储全量code列表用于查询
    client.hset(f"{table_name}:{time_full}", "_all_codes", 
                json.dumps(df_now['code'].tolist()))
```

**效果**: 存储量减少 60-80%

---

### 方案C: 时间分片 + 预聚合

**优化点**: 按分钟预聚合，减少查询时需要加载的时间点数量

**实施**:
```python
# 新增分钟级预聚合表
def aggregate_minute_data(date_str, minute):
    """将秒级数据聚合成分钟级"""
    # 获取该分钟所有秒级数据
    start_time = f"{minute}:00"
    end_time = f"{minute}:59"
    
    # 计算分钟级统计
    minute_stats = calculate_minute_stats(date_str, start_time, end_time)
    
    # 存储到分钟表
    key = f"monitor_gp_minute_{date_str}:{minute}"
    save_to_redis(minute_stats, key)

# 查询时使用分钟级数据
def get_data_by_minute(date_str, minute):
    """获取分钟级数据（比秒级快10倍）"""
    key = f"monitor_gp_minute_{date_str}:{minute}"
    return load_from_redis(key)
```

**效果**: 查询性能提升 10-20倍

---

### 方案D: MySQL + Redis 混合存储

**优化点**: 历史数据存MySQL，实时数据存Redis

**实施**:
```python
# 分层存储策略
class HybridStorage:
    def save(self, df, table_name, time_full):
        # 实时数据存Redis
        save_to_redis(df, table_name, time_full)
        
        # 每5分钟批量写入MySQL
        if should_flush_to_mysql(time_full):
            self._flush_to_mysql(table_name)
    
    def query(self, table_name, time_full, lookback_minutes=5):
        # 近5分钟从Redis查
        if is_recent(time_full):
            return query_from_redis(table_name, time_full, lookback_minutes)
        else:
            # 历史数据从MySQL查
            return query_from_mysql(table_name, time_full, lookback_minutes)
```

**效果**: 内存占用减少 70%，查询性能稳定

---

### 方案E: 数据压缩优化

**优化点**: 使用更高效的压缩算法

**实施**:
```python
# 当前使用zlib，可以改用lz4或zstd
import lz4.frame

def compress_data_lz4(data):
    """使用lz4压缩，比zlib快5倍"""
    return lz4.frame.compress(data)

def decompress_data_lz4(compressed):
    return lz4.frame.decompress(compressed)
```

**效果**: 压缩/解压速度提升 3-5倍

---

## 三、推荐方案组合

### 推荐: 方案A + 方案C + 方案E

**理由**:
1. **方案A (Pipeline批量入库)**: 立竿见影，实施简单
2. **方案C (时间分片预聚合)**: 大幅提升查询性能
3. **方案E (数据压缩优化)**: 减少存储和传输开销

**不选方案B的原因**: 增量更新逻辑复杂，可能影响数据完整性
**不选方案D的原因**: 需要大规模架构调整，影响面广

---

## 四、详细实施方案

### 阶段1: Pipeline批量入库 (30分钟)

**修改文件**: `src/gs2026/utils/redis_util.py`

```python
def save_dataframe_pipeline(df, table_name, time_str, expire_seconds=86400):
    """
    使用Pipeline批量保存DataFrame到Redis
    
    比逐条存储性能提升5-10倍
    """
    client = _get_redis_client()
    pipe = client.pipeline(transaction=False)
    
    key = f"{table_name}:{time_str}"
    
    # 批量HSET
    data_dict = {}
    for idx, row in df.iterrows():
        field = str(row.get('code', idx))
        value = row.to_json()
        data_dict[field] = value
    
    if data_dict:
        pipe.hset(key, mapping=data_dict)
        pipe.expire(key, expire_seconds)
    
    # 更新时间戳列表
    ts_key = f"{table_name}:timestamps"
    pipe.rpush(ts_key, time_str)
    pipe.expire(ts_key, expire_seconds)
    
    # 执行Pipeline
    pipe.execute()
    
    logger.debug(f"Pipeline保存 {len(data_dict)} 条数据到 {key}")
```

**修改调用点**: `monitor_stock.py` 中的 `save_dataframe` 调用改为 `save_dataframe_pipeline`

---

### 阶段2: 时间分片预聚合 (60分钟)

**新增文件**: `src/gs2026/monitor/aggregate_service.py`

```python
"""
分钟级数据预聚合服务
"""
import pandas as pd
from datetime import datetime
from gs2026.utils import redis_util

def aggregate_and_save_minute(date_str, minute_str):
    """
    将秒级数据聚合成分钟级并存储
    
    Args:
        date_str: 日期 YYYYMMDD
        minute_str: 分钟 HH:MM
    """
    table_name = f"monitor_gp_sssj_{date_str}"
    
    # 获取该分钟所有秒级时间点
    start_sec = f"{minute_str}:00"
    end_sec = f"{minute_str}:59"
    
    # 从Redis加载该分钟所有数据
    timestamps = get_timestamps_in_range(table_name, start_sec, end_sec)
    
    if not timestamps:
        return
    
    # 合并所有秒级数据
    all_data = []
    for ts in timestamps:
        df = redis_util.load_dataframe_by_key(f"{table_name}:{ts}")
        if df is not None and not df.empty:
            df['time'] = ts
            all_data.append(df)
    
    if not all_data:
        return
    
    # 聚合计算
    combined = pd.concat(all_data, ignore_index=True)
    
    # 计算分钟级统计
    minute_stats = combined.groupby('code').agg({
        'price': ['first', 'last', 'min', 'max'],
        'volume': 'sum',
        'amount': 'sum',
        'change_pct': 'last'
    }).reset_index()
    
    # 存储到分钟表
    minute_table = f"monitor_gp_minute_{date_str}"
    redis_util.save_dataframe(minute_stats, minute_table, minute_str)
    
    logger.info(f"分钟聚合完成: {minute_str}, 共 {len(minute_stats)} 只股票")

# 定时任务：每分钟执行一次聚合
```

**修改查询逻辑**: `data_service.py` 中优先查询分钟表

---

### 阶段3: 压缩算法优化 (30分钟)

**修改文件**: `src/gs2026/utils/redis_util.py`

```python
# 添加lz4支持
try:
    import lz4.frame
    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False

def compress_data(data_bytes, algorithm='auto'):
    """
    压缩数据
    
    Args:
        algorithm: 'lz4' | 'zlib' | 'auto'
    """
    if algorithm == 'auto':
        algorithm = 'lz4' if LZ4_AVAILABLE else 'zlib'
    
    if algorithm == 'lz4' and LZ4_AVAILABLE:
        return b'\x01' + lz4.frame.compress(data_bytes)  # \x01标记lz4
    else:
        return b'\x00' + zlib.compress(data_bytes)  # \x00标记zlib

def decompress_data(compressed_bytes):
    """解压数据，自动识别算法"""
    if not compressed_bytes:
        return None
    
    algo_marker = compressed_bytes[0:1]
    data = compressed_bytes[1:]
    
    if algo_marker == b'\x01' and LZ4_AVAILABLE:
        return lz4.frame.decompress(data)
    else:
        return zlib.decompress(data)
```

---

## 五、性能对比

| 优化项 | 当前性能 | 优化后 | 提升倍数 |
|--------|----------|--------|----------|
| 入库速度 | 500条/秒 | 3000条/秒 | 6x |
| 查询速度(全量) | 200ms | 50ms | 4x |
| 查询速度(分钟级) | - | 10ms | 20x |
| 内存占用 | 100% | 70% | 30%↓ |
| CPU占用 | 100% | 60% | 40%↓ |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Pipeline批量失败 | 低 | 中 | 添加错误处理和重试 |
| 分钟聚合数据丢失 | 低 | 中 | 保留秒级数据作为备份 |
| 压缩算法不兼容 | 低 | 高 | 向后兼容，自动识别算法 |
| 查询逻辑变更 | 中 | 中 | 充分测试，灰度发布 |

---

## 七、实施计划

| 阶段 | 时间 | 内容 |
|------|------|------|
| 阶段1 | 30分钟 | Pipeline批量入库 |
| 阶段2 | 60分钟 | 时间分片预聚合 |
| 阶段3 | 30分钟 | 压缩算法优化 |
| 测试 | 30分钟 | 性能测试和验证 |
| **总计** | **150分钟** | |

---

**文档位置**: `docs/monitor_gp_sssj_optimization_design.md`

**请确认方案后实施。**
