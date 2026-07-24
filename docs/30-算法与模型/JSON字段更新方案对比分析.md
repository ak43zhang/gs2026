# JSON字段更新方案对比分析

## 问题背景

目标：更新 `ext_indicators` JSON列中的某几个字段（如 `mkt_shape`, `mkt_shape_detail`）

数据规模：~20万行/天，每行需要更新1-2个JSON字段

## 方案对比

### 方案A：直接UPDATE（当前实现）

```sql
-- 逐行UPDATE
UPDATE `monitor_zq_sssj_20260723`
SET ext_indicators = JSON_SET(
    COALESCE(ext_indicators, '{}'),
    '$.mkt_shape', '单边下行',
    '$.mkt_shape_detail', '{"detail": "xxx"}'
)
WHERE bond_code = '123456' AND time = '09:30:03'
```

**实现方式**：
```python
for upd in updates:
    set_expr = "ext_indicators"
    for field, value in upd['field_values'].items():
        set_expr = f"JSON_SET({set_expr}, '$.{field}', %s)"
    sql = f"UPDATE ... SET ext_indicators = {set_expr} WHERE ..."
    conn.execute(sql, params)
```

---

### 方案B：临时表+批量UPDATE（借鉴backfill_unified.py）

```sql
-- 1. 创建临时表（列存储）
CREATE TABLE _temp_json_xxx (
    bond_code VARCHAR(20),
    time VARCHAR(20),
    mkt_shape TEXT,           -- 每个字段一列
    mkt_shape_detail TEXT,
    PRIMARY KEY (bond_code, time)
);

-- 2. 批量插入临时表
INSERT INTO _temp_json_xxx VALUES (...), (...), ...;

-- 3. 批量UPDATE JOIN
UPDATE `monitor_zq_sssj_20260723` t
INNER JOIN _temp_json_xxx s ON t.bond_code = s.bond_code AND t.time = s.time
SET t.ext_indicators = JSON_SET(
    COALESCE(t.ext_indicators, '{}'),
    '$.mkt_shape', s.mkt_shape,
    '$.mkt_shape_detail', s.mkt_shape_detail
);

-- 4. 删除临时表
DROP TABLE _temp_json_xxx;
```

**实现方式**：
```python
# 1. 数据透视：行存储→列存储
df_pivot = df.pivot(index=['bond_code', 'time'], 
                    columns='field_name', 
                    values='field_value')

# 2. 创建临时表+批量插入
df_pivot.to_sql(temp_table, engine, if_exists='append', 
               index=False, method='multi', chunksize=1000)

# 3. 批量UPDATE JOIN
UPDATE ... INNER JOIN ... SET ...

# 4. 清理临时表
DROP TABLE temp_table
```

---

## 详细对比

| 维度 | 方案A：直接UPDATE | 方案B：临时表+批量UPDATE | 结论 |
|------|------------------|------------------------|------|
| **SQL语句数量** | 20万条（逐行） | 1条（批量） | B优 |
| **网络往返次数** | 20万次 | 3次（创建+插入+更新+删除） | B优 |
| **事务开销** | 20万次事务提交 | 1次事务提交 | B优 |
| **MySQL执行效率** | 单条简单，但总量大 | 单条复杂，但总量小 | B优 |
| **JSON_SET复杂度** | 每行1-2个字段 | 批量1-2个字段 | 相当 |
| **内存使用** | 低（逐行处理） | 中（临时表+DataFrame） | A优 |
| **代码复杂度** | 简单 | 较复杂（临时表管理） | A优 |
| **错误处理** | 逐行，单点失败影响小 | 批量，单点失败影响大 | A优 |
| **并发安全** | 高（行级锁） | 中（表级锁风险） | A优 |
| **适用数据量** | 小数据量（<1万行） | 大数据量（>1万行） | 看规模 |

---

## 性能测试估算

### 场景：20万行，更新2个JSON字段

**方案A：直接UPDATE**
```
20万行 × 2ms/行（估算） = 400秒 ≈ 6.7分钟
+ 网络往返 20万次
+ 事务开销 20万次
实际预估：8-10分钟
```

**方案B：临时表+批量UPDATE**
```
创建临时表：0.1秒
批量插入：20万行 / 1000行每批 = 200批 × 0.5秒 = 100秒
批量UPDATE：1次 × 30秒（估算）= 30秒
删除临时表：0.1秒
实际预估：2-3分钟
```

**速度提升**：3-4x

---

## 关键问题分析

### 问题1：JSON_SET链式复杂度

**方案A**：
```sql
-- 每行一个JSON_SET链
JSON_SET(JSON_SET(ext_indicators, '$.f1', v1), '$.f2', v2)
-- 2个字段 = 2层嵌套
```

**方案B**：
```sql
-- 批量一个JSON_SET链
JSON_SET(JSON_SET(ext_indicators, '$.f1', s.f1), '$.f2', s.f2)
-- 同样是2层嵌套，但只做一次
```

**结论**：JSON_SET复杂度相当，但方案B只做一次

---

### 问题2：临时表开销

**创建临时表开销**：
- 磁盘IO：创建表结构
- 内存：临时表缓存
- 估算：0.1-0.5秒

**批量插入开销**：
- `to_sql` with `method='multi'`：高效批量插入
- 估算：1000行/0.5秒

**总体临时表开销**：可接受（<5%总时间）

---

### 问题3：错误处理

**方案A**：
- 优点：逐行失败，不影响其他行
- 缺点：失败20万次中的某一行，难定位

**方案B**：
- 优点：批量原子操作
- 缺点：单点失败，整批失败
- **缓解**：分批UPDATE（1000行/批）

---

## 推荐方案

### 结论：方案B（临时表+批量UPDATE）更优

**核心理由**：
1. **数据量**：20万行属于大数据量，批量优势明显
2. **速度**：预估3-4x提升（10分钟→2-3分钟）
3. **网络**：减少20万次网络往返
4. **事务**：减少20万次事务开销

**关键优化**：
1. **分批UPDATE**：每1000行一批，避免单点失败影响全部
2. **列存储**：临时表按字段分列，UPDATE语句简洁
3. **数据预处理**：去重+类型转换，保证数据质量

---

## 实施建议

### 推荐实现（方案B+分批）

```python
def _bulk_update_json_fields(engine, table_name, df_updates, target_fields):
    """
    批量UPDATE JSON字段（临时表+分批UPDATE）
    
    优化点：
    1. 数据透视：行→列存储
    2. 分批UPDATE：1000行/批，避免超时和单点失败
    3. 错误隔离：单批失败不影响其他批
    """
    # 1. 数据预处理
    df = df_updates.drop_duplicates(subset=['bond_code', 'time'], keep='last')
    df_pivot = df.pivot(index=['bond_code', 'time'], 
                        columns='field_name', 
                        values='field_value').reset_index()
    
    # 2. 创建临时表
    temp_table = f"_temp_json_{int(time.time() * 1000)}"
    # ... 创建表 ...
    
    # 3. 批量插入
    df_pivot.to_sql(temp_table, engine, if_exists='append', 
                   index=False, method='multi', chunksize=1000)
    
    # 4. 分批UPDATE（关键优化）
    BATCH_SIZE = 1000
    for batch_start in range(0, len(df_pivot), BATCH_SIZE):
        batch_df = df_pivot.iloc[batch_start:batch_start + BATCH_SIZE]
        
        # 创建批次临时表
        batch_temp = f"{temp_table}_batch_{batch_start}"
        batch_df.to_sql(batch_temp, engine, if_exists='replace', ...)
        
        # 批次UPDATE
        UPDATE main_table t
        INNER JOIN batch_temp s ON ...
        SET t.ext_indicators = JSON_SET(...)
        
        # 清理批次表
        DROP TABLE batch_temp
    
    # 5. 清理主临时表
    DROP TABLE temp_table
```

---

## 最终建议

| 数据量 | 推荐方案 | 理由 |
|--------|---------|------|
| < 1万行 | 方案A（直接UPDATE） | 简单， overhead小 |
| 1-10万行 | 方案B（批量UPDATE） | 平衡，2-3x提升 |
| > 10万行 | 方案B+分批（1000行/批） | 必须，3-4x提升 |

**当前场景（20万行）**：强烈推荐 **方案B+分批**

---

**等待用户审核通过后实施。**
