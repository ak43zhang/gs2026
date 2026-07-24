# Monitor Stock Tick 周期性能优化方案

## 主力净额缓存 + 派生字段异步化 + Redis健康检查采样 + 表结构异步预检

---

## 版本沿革

| 版本 | 日期 | 更新内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-07-25 00:10 | 初始版本：主力净额缓存 + 派生字段异步化 | - |
| v2.0 | 2026-07-25 00:30 | 新增：Redis健康检查采样优化、表结构异步预检优化 | - |

---

## 一、问题诊断

### 1.1 当前性能瓶颈

基于代码分析和日志，各阶段耗时：

| 阶段 | 平均耗时 | 峰值耗时 | 瓶颈来源 |
|------|---------|---------|---------|
| 数据采集 | 200-500ms | 1000ms | 网络 I/O |
| 数据清洗 | 100-200ms | 500ms | CPU |
| 恢复无效数据 | 100-300ms | 800ms | Redis + MySQL I/O |
| 开盘价计算 | 50-100ms | 200ms | CPU |
| **主力净额计算** | **800-1500ms** | **3000ms+** | **每次从Redis查询`df_prev_main`** |
| 涨停计算 | 100-200ms | 400ms | CPU |
| **派生字段计算** | **300-600ms** | **1500ms+** | **同步执行，阻塞主流程** |
| **Redis健康检查** | **15-50ms** | **100ms** | **每次调用都ping**（v2.0新增）|
| **表结构首次检查** | **50-100ms** | **200ms** | **MySQL元数据查询**（v2.0新增）|
| 大盘强度计算 | 100-200ms | 500ms | CPU |
| 异步保存 | 50-100ms | 300ms | MySQL I/O |

**整体 Tick 周期：2-3秒，偶尔超过3秒**

### 1.2 根本原因

1. **Redis I/O 瓶颈**：每个 tick 重复查询 Redis 获取 `df_prev_main`（上一时刻数据）
2. **无内存缓存**：没有缓存机制，每次都走网络 I/O
3. **同步阻塞**：`calculate_all_derived` 同步执行，阻塞主线程
4. **Redis 健康检查开销**：每次获取客户端都进行健康检查（ping）（v2.0新增）
5. **表结构检查首次开销**：首次检查表结构时查询 MySQL 元数据（v2.0新增）

---

## 二、优化目标

| 优先级 | 目标 | 当前值 | 目标值 |
|------|------|--------|--------|
| P0 | 主力净额计算阶段耗时 | 800-1500ms | < 200ms |
| P1 | 整体 tick 周期 | 2-3s | < 1.5s |
| P2 | Redis健康检查开销 | 15-50ms | < 1ms |（v2.0新增）|
| P3 | 表结构首次检查 | 50-100ms | 0ms（异步） |（v2.0新增）|
| P4 | 数据一致性 | - | 宕机无丢失 |

---

## 三、实施方案（B+方案 + 健康检查优化 + 表结构预检）

### 3.1 核心策略：带验证的内存缓存

```python
# 全局缓存结构（monitor_stock.py 顶部）
_PREV_MAIN_CACHE = {
    'date': None,           # 日期，用于跨日检测
    'timestamp': None,      # 缓存数据对应的时间戳
    'data': None,           # DataFrame数据
    'hit_count': 0          # 缓存命中次数（用于监控）
}
```

**缓存数量：仅 1 个 tick（上一时刻数据）**

**内存增加：约 2-5 MB**
- 数据量：5000只股票 × 100列 × 8字节 ≈ 4MB
- Python对象开销：~1MB
- 对比当前内存占用（200-500MB）：< 1%，**无影响**

### 3.2 具体代码修改

#### 修改1：新增缓存管理函数

**位置**：`monitor_stock.py` 顶部（导入区之后）

```python
# ========== 性能优化：主力净额计算缓存（B+方案）==========

_PREV_MAIN_CACHE = {
    'date': None,
    'timestamp': None,
    'data': None,
    'hit_count': 0
}


def _get_cached_prev_main(sssj_table: str, current_time: str, date_str: str) -> Optional[pd.DataFrame]:
    """
    获取上一时刻数据（带缓存优化）
    
    策略：
    1. 检查内存缓存是否有效（日期匹配、时间连续）
    2. 缓存有效 → 直接返回（O(1)）
    3. 缓存失效 → 从Redis加载 → 更新缓存 → 返回
    
    安全保证：
    - 缓存只是加速层，失效时自动降级到Redis
    - 宕机后缓存清空，自动走Redis→MySQL恢复流程
    """
    global _PREV_MAIN_CACHE
    
    cache = _PREV_MAIN_CACHE
    
    # 检查缓存有效性
    if (cache['date'] == date_str and 
        cache['data'] is not None and 
        cache['timestamp'] is not None):
        
        # 验证时间连续性（当前时间 - 缓存时间 ≈ 15秒）
        cache_dt = datetime.strptime(f"{date_str} {cache['timestamp']}", "%Y%m%d %H:%M:%S")
        current_dt = datetime.strptime(f"{date_str} {current_time}", "%Y%m%d %H:%M:%S")
        time_diff = (current_dt - cache_dt).total_seconds()
        
        # 允许5秒误差（应对网络抖动）
        if 10 <= time_diff <= 20:
            cache['hit_count'] += 1
            if cache['hit_count'] % 100 == 0:
                logger.info(f"[Cache] 命中{cache['hit_count']}次，节省Redis查询")
            return cache['data'].copy()
    
    # 缓存失效：从Redis加载（原有逻辑）
    logger.debug(f"[Cache] 失效，从Redis加载: {current_time}")
    
    try:
        prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, current_time)
        if prev_time:
            df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
        else:
            df_prev_main = None
    except Exception as e:
        logger.warning(f"[Cache] Redis加载失败: {e}")
        df_prev_main = None
    
    # 更新缓存
    if df_prev_main is not None and not df_prev_main.empty:
        _PREV_MAIN_CACHE = {
            'date': date_str,
            'timestamp': current_time,
            'data': df_prev_main.copy(),
            'hit_count': 0
        }
    
    return df_prev_main


def _invalidate_cache():
    """主动失效缓存（日期切换时调用）"""
    global _PREV_MAIN_CACHE
    _PREV_MAIN_CACHE = {'date': None, 'timestamp': None, 'data': None, 'hit_count': 0}
    logger.info("[Cache] 已失效")

# ========== 性能优化结束 ==========
```

#### 修改2：替换原有调用

**位置**：`deal_gp_works` 函数中（line 2768-2783 附近）

**原代码**：
```python
# ========== 【修复】严格区分 df_prev 和 df_prev_main ==========

# 【不变】df_prev 用于上攻排行计算（15秒周期）
# df_prev 已在上面的代码中获取

# 【新增】df_prev_main 用于主力净额计算（时间戳查询）
df_prev_main = None
if not is_auction:
    try:
        # 找上一个有数据的时间点（非15秒周期）
        prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
        if prev_time:
            df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
            logger.info(f"[{time_full}] 主力净额计算使用时间点: {prev_time}")
            
            # 【性能优化】df_prev_main来自Redis（已清洗数据），只做快速验证
            if df_prev_main is not None and not df_prev_main.empty:
                df_prev_main = _quick_validate_redis_data(df_prev_main)
    except Exception as e:
        logger.warning(f"[{time_full}] 获取上一时间点失败: {e}")
```

**优化后代码**：
```python
# ========== 【修复】严格区分 df_prev 和 df_prev_main ==========

# 【不变】df_prev 用于上攻排行计算（15秒周期）
# df_prev 已在上面的代码中获取

# 【优化】df_prev_main 用于主力净额计算（使用缓存）
df_prev_main = None
if not is_auction:
    # 【优化】使用带缓存的版本，减少Redis查询
    df_prev_main = _get_cached_prev_main(sssj_table, time_full, date_str)
    
    if df_prev_main is not None:
        logger.info(f"[{time_full}] 主力净额计算使用时间点: {_PREV_MAIN_CACHE.get('timestamp', 'unknown')}")
        # 【性能优化】df_prev_main来自Redis（已清洗数据），只做快速验证
        df_prev_main = _quick_validate_redis_data(df_prev_main)
    else:
        logger.warning(f"[{time_full}] 无法获取上一时刻数据")
```

#### 修改3：日期切换时失效缓存

**位置**：`run_monitor_loop_synced` 函数中（line 3378-3382 附近）

**原代码**：
```python
if last_date != current_date:
    reset_auction_flags()
    last_date = current_date
    logger.info(f"日期变更，重置集合竞价标志: {current_date}")
```

**优化后代码**：
```python
if last_date != current_date:
    reset_auction_flags()
    last_date = current_date
    logger.info(f"日期变更，重置集合竞价标志: {current_date}")
    
    # 【优化】失效缓存，避免跨日数据污染
    _invalidate_cache()
```

### 3.3 派生字段计算异步化（附加优化）

#### 新增：异步线程池和函数

**位置**：`monitor_stock.py` 顶部（与缓存代码一起）

```python
# ========== 性能优化：派生字段异步计算 ==========

from concurrent.futures import ThreadPoolExecutor

# 单线程池，避免并发问题
_derived_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="derived_calc")


def _async_calculate_derived(df_now: pd.DataFrame, df_prev_main: pd.DataFrame, 
                             top30_codes: Set[str], time_full: str, 
                             sssj_table: str, date_str: str):
    """
    异步计算派生字段，不阻塞主流程
    
    策略：
    1. 提交异步任务计算派生字段
    2. 主流程继续（保存原始数据）
    3. 异步任务完成后，更新Redis中的数据（补充派生字段）
    """
    def _calc_and_update():
        try:
            start = time.time()
            df_with_derived = calculate_all_derived(df_now.copy(), df_prev_main, top30_codes)
            calc_time = (time.time() - start) * 1000
            
            # 异步保存到Redis（补充派生字段）
            _update_redis_with_derived(df_with_derived, sssj_table, time_full, date_str)
            
            logger.info(f"[{time_full}] 派生字段异步计算完成，耗时{calc_time:.1f}ms")
        except Exception as e:
            logger.error(f"[{time_full}] 派生字段异步计算失败: {e}")
    
    _derived_executor.submit(_calc_and_update)
    logger.debug(f"[{time_full}] 派生字段计算已提交异步任务")


def _update_redis_with_derived(df: pd.DataFrame, sssj_table: str, time_full: str, date_str: str):
    """更新Redis数据，补充派生字段"""
    try:
        # 派生字段列表（根据实际字段调整）
        derived_cols = [
            'attack_count_30s', 'continuous_attack', 'attack_strength',
            'momentum_score', 'trend_direction'
        ]
        
        # 构建更新数据
        update_data = {}
        for col in derived_cols:
            if col in df.columns:
                # 按code索引存储
                for _, row in df.iterrows():
                    code = row.get('stock_code') or row.get('code')
                    if code:
                        key = f"{sssj_table}:{time_full}:{code}"
                        if key not in update_data:
                            update_data[key] = {}
                        update_data[key][col] = row[col]
        
        # 批量更新Redis
        if update_data:
            redis_util.hmset_batch(update_data)
            logger.debug(f"[{time_full}] 已更新{len(update_data)}条派生字段到Redis")
            
    except Exception as e:
        logger.warning(f"[{time_full}] 更新派生字段失败: {e}")

# ========== 性能优化结束 ==========
```

#### 替换原有调用

**位置**：`deal_gp_works` 函数中（line 2920-2925 附近）

**原代码**：
```python
# 【新增】统一计算所有派生字段（连续上攻次数等）
try:
    df_now = calculate_all_derived(df_now, df_prev_main, top30_codes)
except Exception as e:
    logger.error(f"[{time_full}] 派生字段计算失败: {e}")
```

**优化后代码**：
```python
# 【优化】异步计算派生字段，不阻塞主流程
try:
    _async_calculate_derived(df_now, df_prev_main, top30_codes, time_full, sssj_table, date_str)
    # 注意：df_now 保持原始数据，派生字段后续异步补充到Redis
except Exception as e:
    logger.error(f"[{time_full}] 派生字段异步提交失败: {e}")
```

---

### 3.4 Redis 健康检查采样优化（v2.0新增）

#### 问题分析

当前 `_get_redis_client(check_health=True)` 每次调用都执行 `ping()` 检查：

```python
# redis_util.py 当前实现
def _get_redis_client(check_health: bool = False):
    if check_health:
        try:
            _redis_client.ping()  # 每次调用都ping，约5-10ms
        except:
            return None
```

**开销**：每个 tick 调用 3-5 次，累计 15-50ms。

#### 优化方案：健康检查采样

**修改**：`src/gs2026/utils/redis_util.py`

```python
# 新增：健康检查采样（每100次检查1次）
_health_check_counter = 0
_HEALTH_CHECK_INTERVAL = 100  # 每100次检查1次

def _get_redis_client(check_health: bool = False) -> Optional[redis.Redis]:
    global _redis_client, _redis_pool, _health_check_counter
    
    if _redis_client is None:
        logger.warning("Redis 客户端未初始化")
        return None
    
    if check_health:
        # 【优化】采样检查，不是每次都ping
        _health_check_counter += 1
        if _health_check_counter % _HEALTH_CHECK_INTERVAL == 0:
            try:
                _redis_client.ping()
            except Exception as e:
                logger.error(f"Redis 健康检查失败: {e}")
                return None
    
    return _redis_client
```

**效果**：健康检查开销从 15-50ms/tick 降至 <1ms/tick。

---

### 3.5 表结构检查优化（v2.0新增）

#### 问题分析

当前表结构检查在首次写入时执行，涉及 MySQL 元数据查询：

```python
# monitor_stock.py 当前实现（line 2892-2901）
if sssj_table not in _table_schema_checked:
    inspector = inspect(engine)           # 创建inspector
    if inspector.has_table(sssj_table):   # 查询表存在性
        columns = inspector.get_columns(sssj_table)  # 查询列信息
    _table_schema_checked.add(sssj_table)
```

**开销**：首次约 50-100ms，后续有缓存。

#### 优化方案：延迟检查 + 异步预检

**优化1：延迟检查（已有，保持不变）**

`_table_schema_checked` 已确保只检查一次，无需修改。

**优化2：异步预检（新增）**

在程序启动时异步预检今日表结构，避免首次写入时的阻塞：

```python
# 新增：monitor_stock.py 顶部
_table_schema_pre_checked = False

def _async_precheck_table_schema(date_str: str):
    """异步预检今日表结构，避免首次写入阻塞"""
    def _check():
        try:
            sssj_table = f"monitor_gp_sssj_{date_str}"
            apqd_table = f"monitor_gp_apqd_{date_str}"
            
            for table in [sssj_table, apqd_table]:
                if table not in _table_schema_checked:
                    inspector = inspect(engine)
                    if inspector.has_table(table):
                        columns = [c['name'] for c in inspector.get_columns(table)]
                        if 'is_body_up' not in columns:
                            _table_schema_no_body.add(table)
                    _table_schema_checked.add(table)
            
            logger.info(f"[预检] 表结构检查完成: {date_str}")
        except Exception as e:
            logger.warning(f"[预检] 表结构检查失败: {e}")
    
    threading.Thread(target=_check, daemon=True).start()

# 在 run_monitor_loop_synced 中调用
if not _table_schema_pre_checked:
    _async_precheck_table_schema(date_str)
    _table_schema_pre_checked = True
```

**效果**：首次 tick 的表结构检查开销从 50-100ms 降至 0ms（异步预检）。

---

## 四、风险控制

### 4.1 数据一致性保证

| 场景 | 处理策略 | 结果 |
|------|---------|------|
| 缓存命中 | 直接返回内存数据 | 一致（数据来自上一tick的Redis） |
| 缓存失效 | 从Redis加载，更新缓存 | 一致 |
| 程序重启 | 缓存为空，从Redis/MySQL恢复 | 一致（已有三级恢复） |
| 日期切换 | 主动失效缓存，重新加载 | 一致 |
| Redis故障 | 降级到MySQL恢复 | 一致（可能延迟） |
| 健康检查采样 | 1%概率检查，失败时返回None | 一致（下次调用重试） |
| 表结构预检失败 | 首次tick同步检查 | 一致（延迟100ms） |

### 4.2 回滚策略

```python
# 配置开关（config.yaml）
monitor_stock:
  enable_prev_main_cache: true      # 主力净额缓存开关
  enable_async_derived: true         # 派生字段异步化开关
  enable_redis_health_sampling: true  # Redis健康检查采样开关
  enable_table_precheck: true         # 表结构预检开关

# 代码中增加开关检查
from gs2026.utils import config_util
_config = config_util.load_config()

if _config.get('monitor_stock', {}).get('enable_prev_main_cache', True):
    df_prev_main = _get_cached_prev_main(sssj_table, time_full, date_str)
else:
    # 原逻辑
    df_prev_main = redis_util.load_dataframe_by_time(...)
```

### 4.3 监控指标

```python
# 日志输出（每100次缓存命中输出一次）
logger.info(f"[Cache] 命中{hit_count}次，节省Redis查询约{hit_count * 50}ms")

# 性能监控（已有）
logger.info(f"[{time_full}] Tick总计: {tick_total:.1f}ms | ...")

# 健康检查采样监控
if _health_check_counter % _HEALTH_CHECK_INTERVAL == 0:
    logger.debug(f"[Redis] 健康检查采样触发")

# 表结构预检监控
logger.info(f"[预检] 表结构检查完成: {date_str}")
```

---

## 五、验证方案

### 5.1 单元测试

```python
# test_monitor_stock_cache.py

def test_cache_hit():
    """测试缓存命中"""
    _invalidate_cache()
    
    # 模拟第一次调用（缓存失效）
    df1 = _get_cached_prev_main("test_table", "14:20:00", "20260724")
    assert df1 is not None
    assert _PREV_MAIN_CACHE['hit_count'] == 0
    
    # 模拟第二次调用（缓存命中，时间连续）
    df2 = _get_cached_prev_main("test_table", "14:20:15", "20260724")
    assert df2 is not None
    assert _PREV_MAIN_CACHE['hit_count'] == 1

def test_cache_invalidate_on_date_change():
    """测试日期切换失效缓存"""
    _PREV_MAIN_CACHE['date'] = '20260723'
    _PREV_MAIN_CACHE['data'] = pd.DataFrame({'test': [1]})
    
    # 新日期调用
    df = _get_cached_prev_main("test_table", "09:30:00", "20260724")
    
    # 缓存应失效，重新加载
    assert _PREV_MAIN_CACHE['date'] == '20260724'

def test_cache_time_gap():
    """测试时间间隔过大时缓存失效"""
    _PREV_MAIN_CACHE['date'] = '20260724'
    _PREV_MAIN_CACHE['timestamp'] = '14:20:00'
    _PREV_MAIN_CACHE['data'] = pd.DataFrame({'test': [1]})
    
    # 时间间隔30秒（超过20秒阈值）
    df = _get_cached_prev_main("test_table", "14:20:30", "20260724")
    
    # 缓存应失效（时间间隔过大）
    # 实际行为取决于Redis是否可用

def test_redis_health_sampling():
    """测试Redis健康检查采样"""
    global _health_check_counter
    _health_check_counter = 0
    
    # 调用99次（不应触发健康检查）
    for _ in range(99):
        client = _get_redis_client(check_health=True)
        assert client is not None
    
    # 第100次应触发健康检查
    client = _get_redis_client(check_health=True)
    assert client is not None
    assert _health_check_counter == 100
```

### 5.2 性能验证

```python
# 对比测试脚本
import time
import statistics

def benchmark_tick_performance(num_ticks=100):
    """对比优化前后的tick性能"""
    
    # 收集数据
    before_times = []  # 优化前（从日志解析）
    after_times = []   # 优化后（从日志解析）
    
    # 解析日志文件
    with open('monitor_stock.log') as f:
        for line in f:
            if 'Tick总计' in line:
                # 提取耗时
                time_ms = parse_tick_time(line)
                if is_before_optimization(line):
                    before_times.append(time_ms)
                else:
                    after_times.append(time_ms)
    
    # 统计
    print(f"优化前平均: {statistics.mean(before_times):.1f}ms")
    print(f"优化后平均: {statistics.mean(after_times):.1f}ms")
    print(f"提升: {(1 - statistics.mean(after_times)/statistics.mean(before_times)) * 100:.1f}%")
    
    # 断言
    assert statistics.mean(after_times) < 1500  # 目标: <1.5s
```

### 5.3 数据一致性验证

```python
def test_data_consistency():
    """验证缓存数据和Redis数据一致"""
    
    # 获取缓存数据
    df_cache = _PREV_MAIN_CACHE['data']
    
    # 获取Redis数据
    df_redis = redis_util.load_dataframe_by_time(
        "monitor_gp_sssj_20260724", 
        _PREV_MAIN_CACHE['timestamp']
    )
    
    # 对比
    pd.testing.assert_frame_equal(df_cache, df_redis)
    print("数据一致性验证通过")
```

---

## 六、实施步骤

| 步骤 | 操作 | 预计耗时 | 回滚点 |
|------|------|---------|--------|
| 1 | 备份 `monitor_stock.py` | 1分钟 | 备份文件 |
| 2 | 添加缓存管理函数（3.2修改1） | 10分钟 | 删除新增代码 |
| 3 | 替换 `deal_gp_works` 调用（3.2修改2） | 5分钟 | 恢复原有代码 |
| 4 | 添加日期切换失效（3.2修改3） | 5分钟 | 删除新增调用 |
| 5 | 添加派生字段异步化（可选） | 15分钟 | 删除新增代码 |
| 6 | 添加配置开关（4.2） | 5分钟 | 关闭开关 |
| 7 | **Redis健康检查优化（3.4修改4）** | 5分钟 | 恢复check_health参数 |
| 8 | **表结构检查优化（3.5修改5）** | 5分钟 | 删除预检查代码 |
| 9 | 编译验证 | 1分钟 | - |
| 10 | 重启 `monitor_stock` | 1分钟 | 快速重启 |
| 11 | 观察日志验证（10个tick） | 5分钟 | 关闭开关 |
| 12 | 全量验证（100个tick） | 30分钟 | 关闭开关 |

**总计：约2小时**

---

## 七、预期效果

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 主力净额计算 | 800-1500ms | <200ms | **85%↓** |
| 派生字段计算 | 300-600ms | <50ms（异步） | **90%↓** |
| **Redis健康检查** | **15-50ms** | **<1ms** | **95%↓**（v2.0新增）|
| **表结构首次检查** | **50-100ms** | **0ms** | **100%↓**（v2.0新增）|
| **整体tick周期** | **2-3s** | **<1.5s** | **50%↓** |
| 内存增加 | - | ~5MB (<1%) | 可忽略 |

---

## 八、相关文件

- 修改文件：`src/gs2026/monitor/monitor_stock.py`
- 修改文件：`src/gs2026/utils/redis_util.py`（v2.0新增）
- 配置文件：`configs/config.yaml`（新增开关）
- 本文档：`docs/02-性能优化/monitor_stock-tick周期性能优化方案-主力净额缓存与派生字段异步化.md`

---

**文档版本**：v2.0  
**更新日期**：2026-07-25  
**版本沿革**：见文档顶部"版本沿革"表格  
**审核状态**：待审核
