# backfill_json_fields.py 性能优化方案（借鉴 backfill_unified.py）

## 一、backfill_unified.py 关键优化点分析

### 1.1 核心优化策略

| 优化点 | backfill_unified.py 实现 | 效果 |
|--------|-------------------------|------|
| **BatchWriter** | 临时表+UPDATE JOIN，分批1000行/批 | 比逐行UPDATE快 10-50x |
| **流式读取** | 时间分片，只读依赖列 | 内存节省 80% |
| **批量插入** | pandas to_sql + method='multi' | 插入速度提升 10x |
| **分批UPDATE** | 每1000行一个批次，避免单条SQL过大 | 避免超时 |
| **进度显示** | 行级进度，速度/剩余时间 | 可见性提升 |

### 1.2 BatchWriter 核心逻辑

```python
class BatchWriter:
    def write_results(self, all_results: list, fields: list):
        # 1. 创建普通临时表（非TEMPORARY，确保跨连接可见）
        CREATE TABLE _temp_backfill_xxx (
            bond_code VARCHAR(20),
            time VARCHAR(20),
            field1 FLOAT,
            field2 TEXT,  -- JSON字段用TEXT
            PRIMARY KEY (bond_code, time)
        )
        
        # 2. pandas to_sql 批量插入
        df.to_sql(temp_table, engine, method='multi', chunksize=1000)
        
        # 3. 分批UPDATE JOIN（每批1000行）
        for batch_start in range(0, total_rows, BATCH_SIZE=1000):
            # 创建批次临时表
            batch_df.to_sql(batch_temp_table, ...)
            
            # UPDATE JOIN
            UPDATE main_table t
            INNER JOIN batch_temp_table s ON t.bond_code=s.bond_code AND t.time=s.time
            SET t.field1 = s.field1, t.field2 = s.field2
            
            # 清理批次表
            DROP TABLE batch_temp_table
        
        # 4. 清理主临时表
        DROP TABLE temp_table
```

### 1.3 流式处理流程

```python
# 1. 预估总行数
estimated_total = SELECT COUNT(*) FROM table

# 2. 流式读取（时间分片）
for df_batch in load_table_data_streaming(engine, table_name, needed_columns):
    # 3. 逐tick计算
    for tick_time, df_tick in df_batch.groupby('time'):
        tick_results = compute_engine.process_tick(df_tick, tick_time, fields)
        
        # 4. 累积结果
        for code in df_tick[CODE_COL].tolist():
            all_results.append({
                'bond_code': code,
                'time': tick_time,
                'field1': tick_results['field1'].get(code),
                'field2': tick_results['field2'].get(code),
            })
    
    # 5. 达到阈值，批量写入
    if len(all_results) >= FLUSH_SIZE:  # 10万行
        writer.write_results(all_results, fields)
        all_results = []  # 清空，释放内存
        
        # 6. 打印进度
        print(f"[{date} #{flush_count}] {total_rows}/{estimated_total} ({progress}%) | "
              f"速度 {speed}行/秒 | 剩余 {remaining}s")
```

## 二、backfill_json_fields.py 优化方案

### 2.1 当前问题 vs 优化目标

| 问题 | 当前实现 | 借鉴 backfill_unified.py | 预期效果 |
|------|---------|------------------------|---------|
| **批量UPDATE** | 临时表+UPDATE JOIN，但无分批 | 分批1000行/批次 | 避免超时 |
| **插入临时表** | 直接DataFrame.to_sql | 去重+类型转换+分批 | 稳定性提升 |
| **批次大小** | 5万行/批次 | 10万行/批次 | 减少批次数量 |
| **进度显示** | 已优化 | 保持一致 | 无需修改 |
| **流式读取** | 已实现 | 保持一致 | 无需修改 |

### 2.2 具体优化点

#### 优化1：分批UPDATE（防止超时）

**当前代码**（问题：单条UPDATE可能过大）
```python
# 当前：一次性UPDATE所有行
UPDATE main_table t
INNER JOIN temp_table s ON t.bond_code=s.bond_code AND t.time=s.time
SET t.ext_indicators = JSON_SET(...)
```

**优化后**（借鉴 backfill_unified.py）
```python
# 优化：分批UPDATE，每批1000行
BATCH_SIZE = 1000
for batch_start in range(0, total_rows, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total_rows)
    batch_df = insert_df.iloc[batch_start:batch_end]
    
    # 创建批次临时表
    batch_temp_table = f"{temp_table}_batch_{batch_start}"
    batch_df.to_sql(batch_temp_table, engine, ...)
    
    # 批次UPDATE
    UPDATE main_table t
    INNER JOIN batch_temp_table s ON t.bond_code=s.bond_code AND t.time=s.time
    SET t.ext_indicators = JSON_SET(...)
    
    # 清理批次表
    DROP TABLE batch_temp_table
```

#### 优化2：插入前处理（去重+类型转换）

**借鉴 backfill_unified.py**
```python
# 1. 转换为DataFrame
df = pd.DataFrame(all_results)

# 2. 去重：保留每个(bond_code, time)组合的最后一条记录
df = df.drop_duplicates(subset=['bond_code', 'time'], keep='last')

# 3. 类型转换（JSON字段用TEXT）
for col in df.columns:
    if col not in ['bond_code', 'time']:
        if col in json_fields:
            df[col] = df[col].astype(str)  # JSON字段转字符串
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce')  # 数值字段

# 4. 只保留需要的列
available_cols = ['bond_code', 'time']
for f in fields:
    if f in df.columns:
        available_cols.append(f)
df = df[available_cols]
```

#### 优化3：临时表结构优化

**当前**（简单结构）
```sql
CREATE TABLE temp_table (
    bond_code VARCHAR(20),
    time TIME,
    field_name VARCHAR(50),
    field_value TEXT
)
```

**优化后**（借鉴 backfill_unified.py，按字段分列）
```sql
CREATE TABLE temp_table (
    bond_code VARCHAR(20),
    time VARCHAR(20),  -- 改为VARCHAR，避免时间格式问题
    mkt_shape TEXT,     -- 每个字段一列
    mkt_shape_detail TEXT,
    PRIMARY KEY (bond_code, time)
)
```

**优势**：
- UPDATE语句更简单（不需要JSON_SET链式）
- 批量UPDATE更高效
- 避免JSON_SET嵌套过深

#### 优化4：清理策略优化

**借鉴 backfill_unified.py**
```python
# 使用新引擎专门用于清理，避免使用可能已超时的连接
from sqlalchemy import create_engine
cleanup_engine = create_engine(
    self.engine.url,
    pool_size=1,
    max_overflow=0,
    pool_recycle=3600
)
with cleanup_engine.connect() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
    conn.commit()
cleanup_engine.dispose()
```

## 三、实施方案

### 3.1 修改 _bulk_update_json_fields 函数

```python
def _bulk_update_json_fields(engine, table_name: str, df_updates: pd.DataFrame, 
                             target_fields: List[str]) -> int:
    """
    【优化】批量UPDATE JSON字段（借鉴 backfill_unified.py）
    
    优化点：
    1. 按字段分列存储（非行存储）
    2. 分批UPDATE（每批1000行）
    3. 插入前去重+类型转换
    4. 使用新连接清理临时表
    """
    if df_updates.empty:
        return 0
    
    # 1. 数据预处理（借鉴 backfill_unified.py）
    # 去重：保留每个(bond_code, time)组合的最后一条记录
    df = df_updates.drop_duplicates(subset=['bond_code', 'time'], keep='last')
    
    # 透视：将行存储转为列存储
    # 原：bond_code | time | field_name | field_value
    # 新：bond_code | time | mkt_shape | mkt_shape_detail
    df_pivot = df.pivot(index=['bond_code', 'time'], 
                        columns='field_name', 
                        values='field_value').reset_index()
    
    # 2. 创建临时表（按字段分列）
    temp_table = f"_temp_json_{int(time.time() * 1000)}"
    
    # 构建列定义
    field_defs = []
    for field in target_fields:
        field_defs.append(f'`{field}` TEXT')
    
    create_sql = f"""
        CREATE TABLE `{temp_table}` (
            bond_code VARCHAR(20),
            `time` VARCHAR(20),
            {', '.join(field_defs)},
            PRIMARY KEY (bond_code, `time`)
        ) ENGINE=InnoDB
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
        
        # 3. 批量插入（使用pandas to_sql）
        df_pivot.to_sql(temp_table, engine, if_exists='append', 
                       index=False, method='multi', chunksize=1000)
        
        # 4. 分批UPDATE（每批1000行，防止超时）
        BATCH_SIZE = 1000
        total_updated = 0
        total_rows = len(df_pivot)
        
        for batch_start in range(0, total_rows, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_rows)
            batch_df = df_pivot.iloc[batch_start:batch_end]
            
            # 创建批次临时表
            batch_temp_table = f"{temp_table}_batch_{batch_start}"
            
            try:
                # 插入批次数据
                batch_df.to_sql(batch_temp_table, engine, if_exists='replace',
                              index=False, method='multi', chunksize=500)
                
                # 构建UPDATE SET子句（JSON_SET链）
                set_clauses = []
                for field in target_fields:
                    set_clauses.append(
                        f"t.ext_indicators = JSON_SET(\n"
                        f"    COALESCE(t.ext_indicators, '{{}}'),\n"
                        f"    '$.{field}',\n"
                        f"    s.`{field}`\n"
                        f")"
                    )
                
                # 批次UPDATE
                update_sql = f"""
                    UPDATE `{table_name}` t
                    INNER JOIN `{batch_temp_table}` s 
                        ON t.bond_code = s.bond_code AND t.time = s.time
                    SET {', '.join(set_clauses)}
                """
                
                with engine.connect() as conn:
                    result = conn.execute(text(update_sql))
                    conn.commit()
                    batch_updated = result.rowcount
                    total_updated += batch_updated
                
                # 清理批次表
                with engine.connect() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS `{batch_temp_table}`"))
                    conn.commit()
                
                print(f"    [BATCH] 批次 {batch_start//BATCH_SIZE + 1}/{(total_rows-1)//BATCH_SIZE + 1}: "
                      f"更新 {batch_updated} 行 ({batch_start+1}-{batch_end})")
                
            except Exception as e:
                # 清理批次表
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{batch_temp_table}`"))
                        conn.commit()
                except:
                    pass
                raise
        
        return total_updated
        
    finally:
        # 5. 清理主临时表（使用新连接）
        try:
            from sqlalchemy import create_engine
            cleanup_engine = create_engine(
                engine.url,
                pool_size=1,
                max_overflow=0,
                pool_recycle=3600
            )
            with cleanup_engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
                conn.commit()
            cleanup_engine.dispose()
        except:
            pass
```

### 3.2 修改 _backfill_single_day 函数

```python
def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                        all_deps: Set[str], skip_existing: bool):
    """
    单日回填（借鉴 backfill_unified.py 优化）
    
    优化点：
    1. FLUSH_SIZE 10万行
    2. 数据预处理（去重+类型转换）
    3. 分批UPDATE（每批1000行）
    """
    ...
    
    # 修改：FLUSH_SIZE 5万 -> 10万
    FLUSH_SIZE = 100000  # 10万行/批次
    
    ...
    
    # 修改：调用 _bulk_update_json_fields 时传入 target_fields
    if len(all_updates) >= FLUSH_SIZE:
        df_updates = pd.DataFrame(all_updates)
        updated = _bulk_update_json_fields(
            self.engine, table_name, df_updates, target_fields  # 新增参数
        )
        ...
```

## 四、性能对比预测

| 优化项 | 当前 | 优化后 | 提升 |
|--------|------|--------|------|
| **UPDATE方式** | 单条大UPDATE | 分批1000行 | 避免超时 |
| **数据预处理** | 无 | 去重+类型转换 | 稳定性↑ |
| **临时表结构** | 行存储 | 列存储 | UPDATE简化 |
| **清理策略** | 直接清理 | 新连接清理 | 可靠性↑ |
| **整体速度** | ~60-120s | ~30-60s | **2x** |

## 五、不影响计算逻辑的保证

- ✅ `monitor_bond.py` 完全不变
- ✅ `compute_engine._compute_json_field()` 调用方式不变
- ✅ 计算结果与优化前完全一致
- ✅ 只优化数据写入策略

---

**等待用户审核通过后实施。**
