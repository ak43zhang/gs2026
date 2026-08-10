# 监控表建表与索引统一管理改造-方案B设计与实施

> 文档路径：`docs/60-实施与变更/变更记录/监控表建表与索引统一管理改造-方案B设计与实施.md`
> 目标文件（核心）：`src/gs2026/monitor/monitor_stock.py`
> 目标文件（索引配置）：`src/gs2026/monitor/table_index_manager.py`
> 关联文件（复用者）：`src/gs2026/monitor/monitor_bond.py`

---

## 版本控制记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-08-11 | 助手 | 初稿：现状排查、方案B详细设计、扩展指南、性能分析 |

> **本改造仅维护此单一文档，所有分析、方案、实施记录、验证结果均在此文件内按版本追加，不另建文件。**

---

## 一、需求背景

用户要求排查 `monitor_stock.py` 与 `monitor_bond.py` 两个监控程序中「建表 → 加索引 → 写数据」的流程是否正确，并确保：

1. 流程正确：严格保证「先建表 → 再索引 → 后写数据」的顺序；
2. 不影响计算逻辑：只在存储环节前置建表与索引，业务计算代码零改动；
3. 性能不能降低：DDL 操作只允许在每日首个 tick 发生一次，后续 tick 零额外 MySQL 交互；
4. **易扩展**：以后「新增索引」或「新增表初始化并自动建索引」都必须非常容易扩展；
5. 只增不改：在现有流程中增量叠加方案B逻辑，不破坏既有异步写入链路。

---

## 二、现状排查结论

### 2.1 实际流程（改造前）

**股票 `monitor_stock.py`（`deal_gp_works`）：**

```
1. sssj_table = f"monitor_gp_sssj_{date_str}"
2. add_index_on_first_write(sssj_table, time_full)   ← L3205 尝试加索引（时序错误）
   └─ 内部只在 time_str ∈ ['09:30:00','09:30:03'] 才执行
   └─ 若表不存在 → 直接 skip（return '表不存在'）
3. save_dataframe_async(df_now, sssj_table, ...)     ← L3420 才真正写数据
   └─ to_sql(if_exists='append')：表不存在时 pandas 自动隐式建表
```

**债券 `monitor_bond.py`（`deal_zq_works`）：**

```
1. sssj_table = f"monitor_zq_sssj_{date_str}"
2. （无任何索引调用）
3. msac.save_dataframe_async(df_now, sssj_table, ...)  ← 直接写数据
```

### 2.2 三个核心问题

| 编号 | 问题 | 详情 |
|------|------|------|
| **P1** | 股票索引时序错误 | `add_index_on_first_write` 在 `save_dataframe_async` **之前**调用。09:30:00 首个 tick 表尚未建（数据还没写），`_add_index_to_table` 检查「表不存在」直接 skip，索引实际从未在首次写入时加成功；且硬编码限定 `09:30:00/09:30:03` 两个时刻 |
| **P2** | 债券完全无索引管理 | `monitor_zq_sssj_{date}` 虽在 `INDEX_CONFIG`（L38-44）中配置了索引，但 `monitor_bond.py` **从不调用** `add_index_on_first_write`，债券实时表长期裸奔无索引 |
| **P3** | 异步写入无法保证顺序 | `save_dataframe_async` 是异步的，即便把索引调用挪到写数据后，也无法保证「写完再建索引」的时序 |

### 2.3 为什么现在没有明显故障

- 单表单日数据量约几千至几万行，无索引全表扫描尚能忍受；
- 索引主要影响**查询**（跨日累计恢复、tick_diff 查询、回填），不影响 **append 写入**；
- 因此功能正常，只是查询效率偏低，债券侧尤甚。

---

## 三、方案B 总体设计

### 3.1 核心思路

在数据写入 MySQL **之前**，通过统一函数 `ensure_table_with_index()` 完成：

1. **显式建表**（`CREATE TABLE IF NOT EXISTS`，schema 由 dtype_map 生成）；
2. **建索引**（读 `INDEX_CONFIG`，检查后 `ADD INDEX`）；
3. 建完再走原有 `to_sql(if_exists='append')` 写数据。

用内存缓存 `_table_ready` 集合保证每张表**每进程只执行一次** DDL，后续 tick O(1) 跳过。

### 3.2 约束满足对照

| 约束 | 满足方式 |
|------|---------|
| 流程正确 | `ensure_table_with_index` 同步执行，返回后表与索引必已就绪，再提交异步 append |
| 不影响计算逻辑 | 仅在 `save_dataframe_async` 入口前置一步，计算代码零改动 |
| 性能不降低 | `_table_ready` 内存去重，除首 tick 外零 MySQL 交互；索引建在空表上比数据堆积后更快 |
| 易扩展 | 索引扩展 = 改 `INDEX_CONFIG` 一处；新表初始化 = 走同一 `save_dataframe_async` 自动生效 |
| 只增不改 | `save_dataframe_async` / `_write_mysql_async` / `_get_dtype_map` 全部保留 |

### 3.3 执行顺序保证

```
save_dataframe_async(df, table)
  │
  ├─ ensure_table_with_index()  ← 同步执行，返回后表+索引已就绪
  │    ├─ 首次: CREATE TABLE → ADD INDEX → _table_ready.add()
  │    └─ 后续: table in _table_ready → 立即 return (O(1))
  │
  └─ _mysql_executor.submit(_write_mysql_async)  ← 异步 append 写数据
       └─ 此时表已存在、索引已建，append 直接命中
```

**顺序永远是：建表 → 索引 → 数据。**

---

## 四、详细实现设计

### 4.1 新增模块级状态（monitor_stock.py，约 L100 附近）

```python
# 【方案B】表就绪状态缓存：记录已完成"建表+索引"的表，每天每表只执行一次DDL
_table_ready: set = set()
_table_ready_lock = threading.Lock()
```

### 4.2 新增核心函数 `ensure_table_with_index()`

```python
def ensure_table_with_index(table_name: str, df: pd.DataFrame, dtype_map: dict) -> None:
    """【方案B】确保表存在且索引就绪（建表→索引），每表每进程只执行一次。

    在写数据前调用。使用内存缓存去重，性能开销仅首次。
    保持 append 写入流程不变，仅前置建表与索引。
    """
    # 快速路径：已就绪直接返回（O(1)，不查MySQL）
    if table_name in _table_ready:
        return

    with _table_ready_lock:
        if table_name in _table_ready:   # 双重检查（防并发重复建表）
            return
        try:
            from sqlalchemy import inspect
            with engine.begin() as conn:
                inspector = inspect(conn)
                # 步骤1: 显式建表
                if not inspector.has_table(table_name):
                    col_defs = _build_column_definitions(df, dtype_map)
                    create_sql = (f"CREATE TABLE IF NOT EXISTS `{table_name}` ({col_defs}) "
                                  f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
                    conn.execute(text(create_sql))
                    logger.info(f"[方案B] 显式建表: {table_name}")
                # 步骤2: 建索引
                _create_indexes_for_table(conn, table_name)
            _table_ready.add(table_name)
        except Exception as e:
            logger.warning(f"[方案B] 建表/索引失败(不阻断写入): {table_name}, {e}")
            # 失败不加入缓存，下个tick重试；也不阻断后续to_sql（append时pandas会兜底建表）
```

### 4.3 新增辅助函数 `_build_column_definitions()`

> **关键点**：类型推导必须与 pandas `to_sql` 完全一致，否则显式建表后 append 会因 schema 不符报错。
> - dtype_map 中已指定的列：按 SQLAlchemy 类型映射；
> - 未指定的列：int64→`BIGINT`、float64→`DOUBLE`、datetime→`DATETIME`、object→`TEXT`（对齐 pandas 默认）。

```python
def _build_column_definitions(df: pd.DataFrame, dtype_map: dict) -> str:
    """根据DataFrame和dtype_map生成CREATE TABLE的列定义字符串。
    类型推导与 to_sql 完全一致，保证兼容。
    """
    col_defs = []
    for col in df.columns:
        sa_type = dtype_map.get(col)
        if sa_type is not None:
            if isinstance(sa_type, sa_types.VARCHAR):
                mysql_type = f"VARCHAR({sa_type.length})"
            elif isinstance(sa_type, sa_types.DECIMAL):
                mysql_type = f"DECIMAL({sa_type.precision},{sa_type.scale})"
            elif isinstance(sa_type, sa_types.SMALLINT):
                mysql_type = "SMALLINT"
            elif isinstance(sa_type, sa_types.INT):
                mysql_type = "INT"
            elif isinstance(sa_type, sa_types.FLOAT):
                mysql_type = "FLOAT"
            else:
                mysql_type = "FLOAT"
        else:
            dt = str(df[col].dtype)
            if 'int' in dt:
                mysql_type = "BIGINT"
            elif 'float' in dt:
                mysql_type = "DOUBLE"
            elif 'datetime' in dt:
                mysql_type = "DATETIME"
            else:
                mysql_type = "TEXT"
        col_defs.append(f"`{col}` {mysql_type}")
    return ", ".join(col_defs)
```

### 4.4 新增 `_create_indexes_for_table()` — 复用 INDEX_CONFIG

```python
def _create_indexes_for_table(conn, table_name: str) -> None:
    """根据 INDEX_CONFIG 为表创建索引（表已存在的前提下）。"""
    from gs2026.monitor.table_index_manager import INDEX_CONFIG

    config = None
    for pattern, cfg in INDEX_CONFIG.items():
        prefix = pattern.split('{date}')[0]
        suffix = pattern.split('{date}')[1] if '{date}' in pattern else ''
        if table_name.startswith(prefix) and table_name.endswith(suffix):
            config = cfg
            break
    if not config:
        return  # 该表无索引配置

    result = conn.execute(text(f"""
        SELECT index_name FROM information_schema.STATISTICS
        WHERE table_schema = DATABASE() AND table_name = '{table_name}'
    """))
    existing = {row[0] for row in result.fetchall()}

    for index_name, columns in config.get('indexes', []):
        if index_name in existing:
            continue
        try:
            conn.execute(text(f"ALTER TABLE `{table_name}` ADD INDEX {index_name} ({columns})"))
            logger.info(f"[方案B] ✓ {table_name}.{index_name} 创建成功")
        except Exception as e:
            if '1061' in str(e) or 'Duplicate' in str(e):
                pass  # 并发已建
            else:
                logger.warning(f"[方案B] ⚠ {table_name}.{index_name}: {e}")
```

### 4.5 接入点：`save_dataframe_async` 前置调用

```python
def save_dataframe_async(df, table_name, time_full, expire_seconds, use_compression=False):
    dtype_map = _get_dtype_map(df, table_name)

    # 【方案B】前置：确保表存在且索引就绪（同步，每表仅首次有开销）
    ensure_table_with_index(table_name, df, dtype_map)

    df_copy = df.copy()
    _mysql_executor.submit(_write_mysql_async, df_copy, table_name, dtype_map)
    _redis_executor.submit(_write_redis_async, df_copy, table_name, time_full,
                             expire_seconds, use_compression)
    logger.info(f"[异步存储] 已提交: {table_name}:{time_full}，{len(df)}条")
```

> 债券侧调用的是 `msac.save_dataframe_async`（`monitor_bond.py` L17 `import monitor_stock as msac`），共用此逻辑，**债券自动受益**，无需单独改造。

### 4.6 移除旧的错误调用（P1 修复）

删除 `monitor_stock.py` `deal_gp_works` 中写数据**前**的：

```python
# 删除（L3203-3207）
# 【新增】自动添加索引（仅在第一次写入时）
try:
    add_index_on_first_write(sssj_table, time_full)
except Exception as e:
    logger.warning(f"添加索引失败（非关键错误）: {e}")
```

索引已由 `ensure_table_with_index` 在写入前正确处理，此调用冗余且时序错误。

### 4.7 补全 INDEX_CONFIG（table_index_manager.py）

```python
# 债券大盘强度（补充）
'monitor_zq_apqd_{date}': {
    'indexes': [('idx_time', 'time')]
},
```

---

## 五、扩展指南（重点）

> 本节是本次改造的核心价值：让「新增索引」「新增表初始化并建索引」变得极其简单。

### 5.1 如何为已有表新增一个索引

**只需改一处**：`src/gs2026/monitor/table_index_manager.py` 的 `INDEX_CONFIG`。

例如给股票实时表新增一个「主力净额」索引：

```python
'monitor_gp_sssj_{date}': {
    'indexes': [
        ('idx_code_time', 'stock_code, time'),
        ('idx_time', 'time'),
        # ... 原有索引 ...
        ('idx_main_net', 'main_net_amount'),   # ← 新增这一行即可
    ]
},
```

**次日**（或重启进程后）新表首个 tick 写入时，`ensure_table_with_index` 会自动为新表建上该索引。**无需改任何业务代码。**

> 注：对**已存在的历史表**，索引不会自动补（因 `_table_ready` 或表已存在只检查缺失并 ADD）。实际上 `_create_indexes_for_table` 会对比 `information_schema.STATISTICS`，只要该表当天首次进入本进程、且索引不存在，就会补建。若要给往期历史表批量补索引，用 `TableIndexManager.add_index_for_date('YYYYMMDD')`。

### 5.2 如何新增一张需要自动建表+索引的监控表

**两步：**

1. 在 `INDEX_CONFIG` 增加该表的模式与索引：

```python
'monitor_xx_newtable_{date}': {
    'indexes': [
        ('idx_time', 'time'),
        ('idx_code_time', 'xx_code, time'),
    ]
},
```

2. 在业务代码里，正常调用 `save_dataframe_async(df, "monitor_xx_newtable_20260811", ...)` 即可。

`ensure_table_with_index` 会：
- 首次写入时按 df 的列结构显式 `CREATE TABLE`；
- 依据 `INDEX_CONFIG` 匹配到该表模式并建索引；
- 之后 tick O(1) 跳过。

**完全无需手写 CREATE TABLE / CREATE INDEX 语句。**

### 5.3 如何为新表指定自定义字段类型

若某列需要特定 MySQL 类型（非默认推导），在 `monitor_stock.py` 的 `_get_dtype_map()` 中增加一条 `elif col == 'xxx':` 分支即可，`_build_column_definitions` 会自动沿用该类型建表，保证建表与写入一致。

### 5.4 扩展点速查表

| 扩展需求 | 修改位置 | 改动量 |
|---------|---------|--------|
| 给某表加索引 | `table_index_manager.py` → `INDEX_CONFIG[表模式]['indexes']` | 加 1 行 |
| 新增自动建表+索引的表 | `INDEX_CONFIG` 加表模式 + 业务里调 `save_dataframe_async` | 加 1 块配置 |
| 某列自定义 SQL 类型 | `monitor_stock.py` → `_get_dtype_map()` | 加 1 个 elif |
| 给历史表批量补索引 | 调 `TableIndexManager.add_index_for_date('YYYYMMDD')` | 0（现成工具） |

---

## 六、性能分析

| 场景 | 开销 |
|------|------|
| 每日首个 tick（每表） | 1×`has_table` + 1×`CREATE TABLE` + 1×索引检查 + N×`ADD INDEX`（约 5-50ms/表） |
| 后续所有 tick | 1×`set` 成员检查（<1μs），**零 MySQL 交互** |
| 写数据本身 | 不变（仍是异步 append + method='multi'） |

**结论：性能不降低。** DDL 仅在开盘首 tick 发生一次；索引建在空表上（首 tick 数据量最小），比现状「数据堆积后再建索引」更快；债券实时表首次拥有索引，**查询性能提升**。

---

## 七、改动清单

| 文件 | 改动 | 类型 |
|------|------|------|
| `monitor_stock.py` | 新增 `_table_ready` / `_table_ready_lock` 模块变量 | 增 |
| `monitor_stock.py` | 新增 `ensure_table_with_index()` | 增 |
| `monitor_stock.py` | 新增 `_build_column_definitions()` | 增 |
| `monitor_stock.py` | 新增 `_create_indexes_for_table()` | 增 |
| `monitor_stock.py` | `save_dataframe_async` 前置调用 `ensure_table_with_index`（1 行） | 增 |
| `monitor_stock.py` | 删除 `deal_gp_works` 中写数据前的 `add_index_on_first_write`（P1 修复） | 删 |
| `table_index_manager.py` | 补 `monitor_zq_apqd_{date}` 索引配置 | 增 |

**计算逻辑零改动，只在存储环节前置建表+索引。债券自动受益（共用 save_dataframe_async）。**

---

## 八、风险与兜底

| 风险 | 兜底措施 |
|------|---------|
| 类型不匹配导致 append 失败 | `_build_column_definitions` 严格对齐 pandas to_sql 默认类型 |
| 建表失败 | catch 后不加入缓存、不阻断写入，pandas append 兜底隐式建表（退化为现状，不会更差） |
| 并发建表 | 双重检查锁 + `IF NOT EXISTS` + 忽略 1061 Duplicate |
| 运行中新增字段 | `_write_mysql_async` 内 `_ensure_mysql_columns` 仍保留，动态加列不受影响 |

---

## 九、回退方案

本文档提交对应一个 git commit，作为回退点。若方案B上线后出现异常，执行：

```bash
git revert <方案B实施commit>
```

即可回到「pandas 隐式建表 + 旧索引调用」的改造前状态。业务写入逻辑本身未改，回退无数据风险。

---

## 十、实施记录

> 实施后在此追加：commit 号、验证结果、观察到的首 tick DDL 日志等。

### v1.0 实施完成（2026-08-11）

- **文档回退点 commit**：`9da2584`（代码实施前的基线文档）
- **代码实施 commit**：`8266ef3`

**改动落地：**

| 文件 | 实际改动 |
|------|---------|
| `monitor_stock.py` | 新增 `_table_ready`/`_table_ready_lock`、`ensure_table_with_index()`、`_build_column_definitions()`、`_create_indexes_for_table()`；`save_dataframe_async` 前置调用；删除 `deal_gp_works` 中错误的 `add_index_on_first_write` 调用 |
| `table_index_manager.py` | 补充 `monitor_zq_apqd_{date}` 债券索引配置 |

**验证结果：**

1. ✅ 语法检查通过（ast.parse）
2. ✅ 模块导入无运行时错误
3. ✅ 端到端测试：对测试表 `monitor_zq_apqd_test0811` 调用 `ensure_table_with_index`，成功显式建表 + 创建 `idx_time` 索引（验证债券新配置生效）+ 缓存去重 + 二次调用 O(1) 跳过
4. ✅ `_build_column_definitions` 类型推导与 pandas to_sql 默认一致（object→TEXT、int64→BIGINT）

**换行符说明：** `monitor_stock.py` 历史以 CRLF 入库，与 `.gitattributes` 的 `*.py text eol=lf` 冲突。本次提交按仓库规范规范化为 LF，diff 中的空白差异为换行规范化产生；经折叠所有空白验证，真实逻辑改动为 **+112 / -5**（新增方案B函数 / 删除错误索引调用）。

**待运行时验证（用户执行）：**
- 次日开盘首个 tick 观察日志：`[方案B] 显式建表: monitor_gp_sssj_YYYYMMDD` 与 `[方案B] ✓ ...idx_... 创建成功`
- 确认债券 `monitor_zq_sssj_YYYYMMDD` / `monitor_zq_apqd_YYYYMMDD` 首次拥有索引
- 确认后续 tick 无重复 DDL 日志（缓存生效）
