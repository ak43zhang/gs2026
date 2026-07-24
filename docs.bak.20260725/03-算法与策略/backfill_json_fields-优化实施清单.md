# backfill_json_fields.py 优化实施清单

## 一、问题清单

### 1. 报错修复
- [ ] **问题**: `[ERROR] 110073: List argument must consist only of tuples or dictionaries`
- [ ] **原因**: SQLAlchemy `conn.execute(text(sql), params)` 中 params 格式错误
- [ ] **位置**: `_process_bond_worker` 函数中的 UPDATE 语句参数传递
- [ ] **修复**: 将 `params` 改为元组或字典格式

### 2. 备份模式优化
- [ ] **问题**: 备份表已存在时仍重复备份
- [ ] **需求**: 如果备份表已存在，则跳过备份
- [ ] **位置**: `main()` 函数中的备份逻辑
- [ ] **修复**: 添加备份表存在性检查

## 二、优化实施清单（不影响 monitor_bond.py）

### 阶段1：修复现有问题（必须先做）

#### 1.1 修复 SQLAlchemy 参数报错
**文件**: `backfill_json_fields.py`
**函数**: `_process_bond_worker`
**修改内容**:
```python
# 原代码（报错）
params = []
for field, value in upd['field_values'].items():
    set_expr = f"JSON_SET({set_expr}, '$.{field}', %s)"
    params.append(value)
params.extend([bond_code, upd['time']])
conn.execute(text(sql), params)  # ❌ 列表格式错误

# 修复后
tuple_params = []
for field, value in upd['field_values'].items():
    set_expr = f"JSON_SET({set_expr}, '$.{field}', %s)"
    tuple_params.append(value)
tuple_params.extend([bond_code, upd['time']])
conn.execute(text(sql), tuple(tuple_params))  # ✅ 元组格式
```

#### 1.2 修复备份重复问题
**文件**: `backfill_json_fields.py`
**函数**: `main()`
**修改内容**:
```python
# 原代码
conn.execute(text(f"DROP TABLE IF EXISTS `{backup_name}`"))
conn.execute(text(f"CREATE TABLE `{backup_name}` AS SELECT * FROM `{table_name}`"))

# 修复后
# 检查备份表是否已存在
result = conn.execute(text(f"""
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = DATABASE() AND table_name = '{backup_name}'
"""))
if result.fetchone():
    print(f"[BACKUP] 备份表已存在，跳过: {backup_name}")
else:
    conn.execute(text(f"CREATE TABLE `{backup_name}` AS SELECT * FROM `{table_name}`"))
    print(f"[BACKUP] {table_name} -> {backup_name}")
```

### 阶段2：性能优化（参考 backfill_unified.py）

#### 2.1 新增：时间分片流式读取
**文件**: `backfill_json_fields.py`
**新增函数**: `load_table_data_streaming()`
**功能**: 按时间批次读取数据，替代单债券查询
**影响**: 查询次数 400次→24次，减少94%

```python
def load_table_data_streaming(engine, table_name, needed_columns, chunk_time_count=200):
    """
    时间分片流式读取
    
    Args:
        engine: SQLAlchemy引擎
        table_name: 表名
        needed_columns: 需要的列集合
        chunk_time_count: 每批时间点数量（默认200）
    
    Yields:
        pd.DataFrame: 每批数据（按时间排序）
    """
    # 1. 获取所有时间点（轻量查询）
    time_sql = f"SELECT DISTINCT `time` FROM `{table_name}` ORDER BY `time`"
    with engine.connect() as conn:
        result = conn.execute(text(time_sql))
        all_times = [row[0] for row in result.fetchall()]
    
    if not all_times:
        return
    
    # 2. 按时间片批量查询
    for i in range(0, len(all_times), chunk_time_count):
        chunk_times = all_times[i:i + chunk_time_count]
        
        # 构建IN子句
        placeholders = ', '.join([f"'{t}'" for t in chunk_times])
        cols_str = ", ".join([f"`{c}`" for c in needed_columns])
        
        chunk_sql = f"""
            SELECT {cols_str} 
            FROM `{table_name}` 
            WHERE `time` IN ({placeholders}) 
            ORDER BY `time`, `bond_code`
        """
        
        df = pd.read_sql(text(chunk_sql), engine)
        
        if not df.empty:
            yield df
```

#### 2.2 新增：批量UPDATE（JSON字段专用）
**文件**: `backfill_json_fields.py`
**新增函数**: `_bulk_update_json_fields()`
**功能**: 使用临时表+UPDATE JOIN批量更新JSON字段
**影响**: UPDATE次数 192万次→20次，减少99.9%

```python
def _bulk_update_json_fields(engine, table_name, df_updates):
    """
    批量UPDATE JSON字段（使用临时表+UPDATE JOIN）
    
    原理：
    1. 创建临时表 _temp_json_updates
    2. 将更新数据批量写入临时表
    3. UPDATE JOIN：主表 JOIN 临时表，使用JSON_MERGE_PATCH批量更新
    4. 删除临时表
    
    Args:
        engine: SQLAlchemy引擎
        table_name: 目标表名
        df_updates: DataFrame [bond_code, time, field_name, field_value]
    """
    import pandas as pd
    
    if df_updates.empty:
        return 0
    
    temp_table = f"_temp_json_updates_{datetime.now().strftime('%H%M%S')}"
    
    try:
        with engine.connect() as conn:
            # 1. 创建临时表
            conn.execute(text(f"""
                CREATE TABLE `{temp_table}` (
                    bond_code VARCHAR(20),
                    `time` TIME,
                    field_name VARCHAR(50),
                    field_value TEXT
                )
            """))
            
            # 2. 批量写入临时表
            df_updates.to_sql(temp_table, engine, if_exists='append', 
                            index=False, method='multi', chunksize=1000)
            
            # 3. UPDATE JOIN（批量更新JSON字段）
            # 使用JSON_SET链式更新
            update_sql = f"""
                UPDATE `{table_name}` t
                INNER JOIN `{temp_table}` s ON t.bond_code = s.bond_code AND t.time = s.time
                SET t.ext_indicators = JSON_SET(
                    COALESCE(t.ext_indicators, '{{}}'),
                    CONCAT('$.', s.field_name),
                    s.field_value
                )
            """
            result = conn.execute(text(update_sql))
            updated_rows = result.rowcount
            
            conn.commit()
            
            # 4. 清理临时表
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
            conn.commit()
            
            return updated_rows
            
    except Exception as e:
        # 清理临时表
        try:
            with engine.connect() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
                conn.commit()
        except:
            pass
        raise
```

#### 2.3 修改：单日回填流程（流式批次）
**文件**: `backfill_json_fields.py`
**修改函数**: `_backfill_single_day()`
**功能**: 改为流式批次处理，参考 backfill_unified.py
**影响**: 内存可控，进度可见

```python
def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                        all_deps: Set[str], skip_existing: bool):
    """单日回填（流式批次版）"""
    table_name = f"{TABLE_PREFIX}{date_str}"
    print(f"\n[{date_str}] 开始...")
    t0 = time.time()
    
    # 1. 预估总行数
    with self.engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
        estimated_total = result.scalar() or 0
    
    if estimated_total == 0:
        print(f"  [SKIP] 无数据")
        return
    
    print(f"  [INFO] 预估 {estimated_total:,} 行")
    
    # 2. 确定需要的列
    needed_columns = {'bond_code', 'time', 'ext_indicators'}
    needed_columns.update(all_deps)
    
    # 3. 流式读取 + 批次处理
    compute_engine = ComputeEngine()
    all_updates = []  # 累积更新
    FLUSH_SIZE = 100000  # 10万行/批次
    total_rows = 0
    total_updated = 0
    flush_count = 0
    est_flushes = max(1, estimated_total // FLUSH_SIZE)
    
    for df_batch in load_table_data_streaming(self.engine, table_name, needed_columns):
        if df_batch.empty:
            continue
        
        total_rows += len(df_batch)
        
        # 4. 批次计算（同一时间点的所有债券）
        for tick_time, df_tick in df_batch.groupby('time'):
            # 解析ext_indicators
            df_tick['ext_parsed'] = df_tick['ext_indicators'].apply(
                lambda x: json.loads(x) if x else {}
            )
            
            # 逐行计算（保持状态一致性）
            for _, row in df_tick.iterrows():
                ext = row['ext_parsed']
                
                # 检查skip_existing
                if skip_existing and all(f in ext for f in target_fields):
                    deps = {dep: ext.get(dep) for dep in all_deps}
                    compute_engine._update_state(deps)
                    continue
                
                # 提取依赖
                deps = {dep: ext.get(dep) for dep in all_deps}
                compute_engine._update_state(deps)
                
                # 计算字段
                for field_name in target_fields:
                    field_config = self.json_fields.get(field_name)
                    if not field_config:
                        continue
                    
                    # 构建历史
                    history = []
                    if field_config.get('needs_history'):
                        state_var = field_config.get('state_vars', [''])[0].lstrip('_')
                        history = getattr(compute_engine, state_var, [])
                        history = history[:-1] if len(history) > 1 else []
                    
                    # 计算
                    value = compute_engine._compute_json_field(field_name, deps, history)
                    
                    # 累积更新
                    all_updates.append({
                        'bond_code': row['bond_code'],
                        'time': row['time'],
                        'field_name': field_name,
                        'field_value': json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                    })
        
        # 5. 达到批次阈值，执行批量UPDATE
        if len(all_updates) >= FLUSH_SIZE:
            df_updates = pd.DataFrame(all_updates)
            updated = _bulk_update_json_fields(self.engine, table_name, df_updates)
            total_updated += updated
            all_updates = []
            flush_count += 1
            
            # 打印进度
            elapsed = time.time() - t0
            progress = total_rows / estimated_total * 100
            speed = total_rows / elapsed if elapsed > 0 else 0
            remaining = (estimated_total - total_rows) / speed if speed > 0 else 0
            print(f"  [{date_str} #{flush_count}/~{est_flushes}] "
                  f"{total_rows:,}/{estimated_total:,} ({progress:.1f}%) | "
                  f"速度 {speed:.0f}行/秒 | 剩余 {remaining:.0f}s")
    
    # 6. 写入剩余数据
    if all_updates:
        df_updates = pd.DataFrame(all_updates)
        updated = _bulk_update_json_fields(self.engine, table_name, df_updates)
        total_updated += updated
    
    elapsed = time.time() - t0
    speed = total_rows / elapsed if elapsed > 0 else 0
    print(f"  [DONE] {total_rows:,} 行处理, {total_updated} 行更新, "
          f"耗时 {elapsed:.1f}s, 平均 {speed:.0f}行/秒")
```

#### 2.4 删除：债券级worker（不再需要）
**文件**: `backfill_json_fields.py`
**删除函数**: `_process_bond_worker()`
**原因**: 改为流式批次处理，不再需要债券级并行

## 三、实施顺序

```
阶段1（必须先做）:
  ├── 1.1 修复 SQLAlchemy 参数报错
  └── 1.2 修复备份重复问题

阶段2（性能优化）:
  ├── 2.1 新增 load_table_data_streaming()
  ├── 2.2 新增 _bulk_update_json_fields()
  ├── 2.3 修改 _backfill_single_day() 为流式批次
  └── 2.4 删除 _process_bond_worker()
```

## 四、验证清单

### 阶段1验证
- [ ] 运行不报错 `List argument must consist only of tuples or dictionaries`
- [ ] 备份表已存在时跳过备份
- [ ] 备份表不存在时正常创建

### 阶段2验证
- [ ] 查询次数显著减少
- [ ] UPDATE次数显著减少
- [ ] 进度显示正常（行级+批次级）
- [ ] 内存使用可控
- [ ] 结果正确性验证

## 五、回滚方案

1. 备份当前 `backfill_json_fields.py` 为 `backfill_json_fields_v1.py`
2. 实施阶段1和阶段2
3. 如出现问题，替换回原版本

---

**等待用户审核通过后实施。**
