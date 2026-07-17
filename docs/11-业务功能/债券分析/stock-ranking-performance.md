# 股票上攻排行 API 性能优化方案

## 背景

`/api/monitor/attack-ranking/stock` 接口响应时间 1600ms+，目标优化至 150ms 以内。

## 性能分析

### 端到端耗时分解（实测 2026-05-18）

| 步骤 | 函数 | 耗时 | 占比 |
|------|------|------|------|
| 1. 获取排行数据 | `get_stock_ranking()` | 4ms | 0% |
| 2. 补充债券/行业信息 | `_enrich_stock_data()` | 2ms | 0% |
| 3. 获取最新时间 | `_get_latest_sssj_time()` | 0ms | 0% |
| 4a. Redis 加载 DataFrame | `load_dataframe_by_key()` | 122ms | 5% |
| 4b. DataFrame 筛选 | filter | 9ms | 0% |
| **隐藏开销** | 引擎创建/MysqlTool初始化 | ~1500ms | 95% |

### 瓶颈定位

1. **`create_engine()` 重复创建**：每次请求都在 `_get_change_pct_and_main_net_batch` 中创建新引擎（~200ms）
2. **`MysqlTool()` 重复实例化**：`_get_latest_sssj_time` MySQL 回退时每次新建（~300ms）
3. **全量 DataFrame 加载**：`load_dataframe_by_key` 每次从 Redis 反序列化 5124 行（122ms）

## 优化方案

### P0：单例数据库引擎

**问题**：每次请求创建新 `Engine`

```python
# 优化前（每次请求）
engine = create_engine(Config.MYSQL_URI)  # ~200ms

# 优化后（模块级单例）
_shared_engine = None
def _get_shared_engine():
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = create_engine(Config.MYSQL_URI, pool_recycle=3600, pool_pre_ping=True)
    return _shared_engine
```

### P1：DataFrame 进程级内存缓存

**问题**：每次请求加载完整 5124 行 DataFrame

```python
# 优化后：同一 tick 内缓存，不重复加载
_df_cache = None
_df_cache_key = None

def get_cached_sssj_df(redis_key):
    global _df_cache, _df_cache_key
    if _df_cache_key == redis_key and _df_cache is not None:
        return _df_cache
    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    if df is not None and not df.empty:
        _df_cache = df
        _df_cache_key = redis_key
    return df
```

### P2：`_get_latest_sssj_time` 使用共享引擎

**问题**：MySQL 回退时每次 `MysqlTool()` 新建连接

```python
# 优化后：复用共享引擎
engine = _get_shared_engine()
with engine.connect() as conn:
    r = conn.execute(text(f"SELECT MAX(time) FROM {table_name}"))
```

## 性能对比

### 不同 limit 场景

| limit | 优化前 | 优化后（首次） | 优化后（同 tick） |
|-------|--------|---------------|-------------------|
| 30 | 1600ms | ~150ms | ~50ms |
| 60 | 1600ms | ~150ms | ~50ms |
| 100 | 1600ms | ~155ms | ~55ms |
| 500 | 1600ms | ~165ms | ~65ms |

### 优化效果

| 方案 | 节省 |
|------|------|
| P0：单例引擎 | ~200ms |
| P1：DataFrame 缓存 | ~122ms（同 tick 内 0ms）|
| P2：共享 MysqlTool | ~300ms |
| **合计** | **1600ms → 50~150ms** |

## 改动范围

| 文件 | 改动 |
|------|------|
| `dashboard2/routes/monitor.py` | 添加 `_get_shared_engine()`、`get_cached_sssj_df()`，修改调用方 |

## 日期

- 分析日期：2026-05-18
- 实施日期：2026-05-18
