# backfill_json_fields.py 流程分析与优化方案

## 一、当前流程分析

### 1.1 数据获取流程

```
backfill() 
  └── 遍历日期列表
       └── _backfill_single_day(date_str)
            ├── _get_bonds(table_name)  
            │   └── SELECT DISTINCT bond_code FROM table
            │       WHERE ext_indicators IS NOT NULL
            │   【问题】只获取债券代码，不获取数据量信息
            │
            └── ProcessPoolExecutor(workers=8)
                 └── _process_bond_worker(bond_code)
                      ├── 每个worker独立创建连接
                      ├── SELECT time, ext_indicators 
                      │   FROM table WHERE bond_code = :code
                      │   【问题】每只债券单独查询，4800次查询/债券
                      ├── 逐tick计算（内存中）
                      └── 逐行UPDATE（每只债券内逐tick更新）
```

### 1.2 当前问题分析

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| **单债券单查询** | 400只债券 × 4800tick = 400次查询，但每只债券单独连接 | 中 |
| **逐行UPDATE** | 每只债券内逐tick执行UPDATE，非批量 | 高 |
| **无批次概念** | 无法按批次打印进度，内存中全量计算 | 高 |
| **worker粒度** | 按债券并行，tick计算串行，无法利用向量化 | 中 |
| **无流式读取** | 每只债券全量读取到内存，再计算 | 中 |
| **连接管理** | 每个worker独立创建引擎，连接数 = workers | 中 |

### 1.3 与 backfill_unified.py 对比

| 特性 | backfill_unified.py | backfill_json_fields.py(当前) |
|------|---------------------|------------------------------|
| **数据读取** | 时间分片流式读取（200tick/片） | 单债券全量读取 |
| **批次处理** | 10万行/批次，批量UPDATE JOIN | 无批次，逐行UPDATE |
| **进度显示** | 行数/百分比/速度/剩余时间 | 债券数/百分比 |
| **并行粒度** | 日期级并行 | 债券级并行 |
| **内存控制** | 流式，不累积 | 每只债券全量 |
| **更新方式** | 临时表+UPDATE JOIN（批量） | 逐行JSON_SET |

## 二、优化方案

### 2.1 核心设计思想

参考 `backfill_unified.py` 的优化策略：
1. **时间分片**：按时间批次读取，而非按债券
2. **批量计算**：同一时间点所有债券向量化计算
3. **批量写入**：累积到一定量后批量UPDATE
4. **流式处理**：不累积全量数据，处理完即释放

### 2.2 优化后流程

```
backfill()
  └── 遍历日期列表
       └── _backfill_single_day(date_str)
            ├── 预估总行数（SELECT COUNT(*)）
            ├── 时间分片读取（200tick/片）
            │   └── load_table_data_streaming()
            │       ├── 获取所有时间点列表
            │       └── 按时间片批量查询
            │
            ├── 批次计算（向量化）
            │   └── 同一时间点的所有债券一起计算
            │       └── compute_engine.process_tick(df_tick)
            │
            ├── 批次累积（10万行/批次）
            │   └── 达到阈值后批量UPDATE
            │       └── _bulk_update_json_fields()
            │           ├── 创建临时表
            │           ├── 批量INSERT临时表
            │           └── UPDATE JOIN（批量更新JSON字段）
            │
            └── 打印批次进度
                └── [date #batch/est] 行数/百分比/速度/剩余时间
```

### 2.3 关键优化点

#### 优化1：时间分片读取（替代单债券查询）

```python
def load_table_data_streaming(engine, table_name, needed_columns, batch_size=50000):
    """
    时间分片读取，替代原来的单债券查询
    
    原方案：400只债券 × 4800tick = 400次查询
    新方案：4800tick / 200tick每片 = 24次查询
    
    优势：
    - 查询次数减少 94% (400→24)
    - 同一时间点的所有债券一起返回，利于向量化计算
    """
    # 1. 获取所有时间点
    time_sql = "SELECT DISTINCT `time` FROM table ORDER BY `time`"
    all_times = [row[0] for row in conn.execute(time_sql)]
    
    # 2. 按时间片批量查询
    chunk_time_count = 200  # 每片200个时间点
    for i in range(0, len(all_times), chunk_time_count):
        chunk_times = all_times[i:i + chunk_time_count]
        
        # 批量查询该时间片的所有债券数据
        df = pd.read_sql(
            "SELECT * FROM table WHERE time IN (...) ORDER BY time, bond_code",
            engine, params={'times': chunk_times}
        )
        yield df
```

#### 优化2：向量化批次计算（替代逐tick计算）

```python
# 原方案：逐tick计算
for _, row in df.iterrows():  # 逐行
    for field in target_fields:  # 逐字段
        value = compute(...)  # 单值计算

# 新方案：同一时间片批量计算
for tick_time, df_tick in df.groupby('time'):
    # df_tick 包含该时间点的所有债券
    # 向量化计算所有债券的所有字段
    results = compute_engine.process_tick(df_tick, tick_time, fields_set)
```

#### 优化3：批量UPDATE（替代逐行UPDATE）

```python
# 原方案：逐行UPDATE（每只债券4800次UPDATE）
for upd in updates:
    sql = "UPDATE table SET ext_indicators = JSON_SET(...) WHERE bond_code=%s AND time=%s"
    conn.execute(sql, [bond_code, time])

# 新方案：批量UPDATE JOIN（10万行/批次）
def _bulk_update_json_fields(df_updates, table_name):
    """
    使用临时表+UPDATE JOIN批量更新JSON字段
    
    原理：
    1. 创建临时表 _temp_updates
    2. 将更新数据批量写入临时表
    3. UPDATE JOIN：主表 JOIN 临时表，批量更新
    4. 删除临时表
    
    优势：比逐行UPDATE快 10-50x
    """
    # 1. 创建临时表
    CREATE TABLE _temp_updates (
        bond_code VARCHAR(20),
        time TIME,
        field_values JSON
    )
    
    # 2. 批量写入临时表
    INSERT INTO _temp_updates VALUES (...), (...), ...
    
    # 3. UPDATE JOIN（批量更新JSON字段）
    UPDATE table t
    INNER JOIN _temp_updates s ON t.bond_code = s.bond_code AND t.time = s.time
    SET t.ext_indicators = JSON_MERGE_PATCH(t.ext_indicators, s.field_values)
```

#### 优化4：批次进度显示

```python
# 每批次完成后打印进度
if len(all_results) >= FLUSH_SIZE:  # 10万行
    writer.write_results(all_results, target_fields)
    all_results = []
    flush_count += 1
    
    # 打印进度（参考 backfill_unified.py）
    elapsed = time.time() - t0
    progress = total_rows_read / estimated_total * 100
    speed = total_rows_read / elapsed
    remaining = (estimated_total - total_rows_read) / speed
    
    print(f"[{date_str} #{flush_count}/~{est_flushes}] "
          f"{total_rows_read:,}/{estimated_total:,} ({progress:.1f}%) | "
          f"速度 {speed:.0f}行/秒 | 剩余 {remaining:.0f}s")
```

### 2.4 内存控制

| 场景 | 原方案内存 | 新方案内存 | 优化效果 |
|------|-----------|-----------|---------|
| 单债券数据 | 4800行 × 1只 | 200tick × 400只 = 8万行 | 可控 |
| 累积结果 | 无累积，逐行UPDATE | 10万行/批次 | 可控 |
| 峰值内存 | 债券数 × 单债券数据 | 时间片数据 + 批次结果 | 降低80% |

### 2.5 并发控制

| 方案 | 连接数 | 并发粒度 | 风险 |
|------|--------|---------|------|
| 原方案 | workers=8 | 债券级 | 低 |
| 新方案 | 单连接 | 无并发（流式） | 更低 |

**说明**：新方案采用单进程流式处理，避免多进程带来的：
- 连接池竞争
- 进程间通信开销
- 序列化/反序列化成本

## 三、实施方案

### 3.1 修改文件

仅修改 `backfill_json_fields.py`，无需修改其他文件。

### 3.2 新增函数

1. `load_table_data_streaming()` - 时间分片流式读取
2. `_bulk_update_json_fields()` - 批量UPDATE JOIN
3. `BatchWriter` 类（参考 backfill_unified.py）

### 3.3 修改函数

1. `_backfill_single_day()` - 改为流式批次处理
2. 删除 `_process_bond_worker()` - 不再需要债券级worker

### 3.4 代码结构

```python
# 新增：时间分片读取
def load_table_data_streaming(engine, table_name, needed_columns, batch_size=50000):
    ...

# 新增：批量UPDATE
def _bulk_update_json_fields(engine, df_updates, table_name):
    ...

# 修改：单日回填（流式批次）
def _backfill_single_day(self, date_str, target_fields, all_deps, skip_existing):
    # 1. 预估总行数
    # 2. 流式读取（时间分片）
    # 3. 批次计算（向量化）
    # 4. 批次累积
    # 5. 批量UPDATE
    # 6. 打印进度
    ...
```

## 四、预期效果

| 指标 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 查询次数 | 400次/天 | 24次/天 | 94%↓ |
| UPDATE次数 | 192万次/天 | 20次/天 | 99.9%↓ |
| 内存峰值 | 无控制 | 10万行 | 可控 |
| 处理速度 | ~100只/秒 | ~500行/秒 | 5x↑ |
| 进度可见性 | 债券级 | 行级+批次级 | 更细 |
| 超时风险 | 中（逐行UPDATE慢） | 低（批量UPDATE快） | 显著降低 |

## 五、回滚方案

如优化后出现问题，可快速回滚：
1. 备份当前 `backfill_json_fields.py`
2. 优化版本保存为 `backfill_json_fields_v2.py`
3. 出现问题时替换回原版本

---

**等待用户审核通过后实施。**
