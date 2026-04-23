# 涨停行概选股性能优化方案 v2（Redis优先 + 索引优化）

> 创建时间: 2026-04-23 11:52
> 分析对象: 涨停行概选股查询流程
> 核心思路: Redis优先查询，MySQL作为回退

---

## 一、当前架构分析

### 1.1 数据流架构

```
monitor_stock.py (数据采集)
    ↓
    ├── 写入 MySQL: monitor_gp_sssj_{date}, monitor_zq_sssj_{date}
    └── 写入 Redis: {table_name}:{timestamp}, {table_name}:timestamps (List)
    ↓
stock_picker_service.py (数据查询)
    ↓
    └── 当前: 只查询 MySQL
        └── 问题: 未利用Redis缓存，每次都走数据库
```

### 1.2 Redis数据结构

```
# 1. 时间戳列表 (List)
Key: monitor_gp_sssj_{date}:timestamps
Value: ["15:00:00", "14:59:57", "14:59:54", ...]

# 2. 具体数据 (String - JSON)
Key: monitor_gp_sssj_{date}:15:00:00
Value: [{"stock_code": "000001", "price": 10.5, "is_zt": 1, ...}, ...]

# 3. 当前已有索引配置 (table_index_manager.py)
- idx_code_time: stock_code, time
- idx_time: time
# 缺少: idx_is_zt (is_zt字段无索引)
```

### 1.3 当前查询流程问题

| 问题 | 说明 | 影响 |
|------|------|------|
| **未使用Redis** | `get_ztb_tags` 直接查询MySQL | **高** |
| **缺少is_zt索引** | `WHERE is_zt = 1` 全表扫描 | **高** |
| **子查询重复** | `MAX(time)` 每次都执行 | 中 |
| **IN查询性能差** | `stock_code IN (...)` 列表长 | 中 |

---

## 二、优化方案设计

### 方案核心: Redis优先 + 索引补充

```
查询请求
    ↓
【第一层】Redis查询
    ├── 成功: 直接返回
    └── 失败/无数据: 进入第二层
    ↓
【第二层】MySQL查询（带索引优化）
    └── 返回数据 + 异步写入Redis
```

---

## 三、具体实施步骤

### 步骤1: 在 table_index_manager.py 增加 is_zt 索引

**文件**: `src/gs2026/monitor/table_index_manager.py`

```python
# 修改 INDEX_CONFIG，增加 is_zt 索引
INDEX_CONFIG: Dict[str, Dict] = {
    # 股票实时数据表
    'monitor_gp_sssj_{date}': {
        'indexes': [
            ('idx_code_time', 'stock_code, time'),      # 已有
            ('idx_time', 'time'),                        # 已有
            ('idx_is_zt', 'is_zt'),                      # 【新增】涨停标记索引
            ('idx_is_zt_time', 'is_zt, time'),           # 【新增】复合索引
        ]
    },
    # ... 其他表配置不变
}
```

**效果**: 
- `WHERE is_zt = 1` 从全表扫描变为索引扫描
- 预期性能提升: 10-100倍

---

### 步骤2: 在 redis_util.py 增加涨停数据查询函数

**文件**: `src/gs2026/utils/redis_util.py`

```python
def get_zt_stocks_from_redis(date: str, table_type: str = 'stock') -> Optional[List[str]]:
    """
    从Redis获取涨停股票代码列表
    
    Args:
        date: 日期 YYYYMMDD
        table_type: 'stock' 或 'bond'
    
    Returns:
        涨停股票代码列表 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"
    
    # 1. 获取最新时间戳
    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if not ts_data:
        logger.warning(f"Redis无数据: {table_name}")
        return None
    
    timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    
    # 2. 获取该时间点的数据
    key = f"{table_name}:{timestamp}"
    df = load_dataframe_by_key(key)
    
    if df is None or df.empty:
        return None
    
    # 3. 筛选涨停股票
    if 'is_zt' not in df.columns:
        logger.warning(f"数据缺少is_zt字段: {table_name}")
        return None
    
    zt_stocks = df[df['is_zt'] == 1]['stock_code'].tolist()
    logger.info(f"从Redis获取涨停股票: {len(zt_stocks)} 只")
    return zt_stocks


def get_realtime_prices_from_redis(date: str, stock_codes: List[str], 
                                   table_type: str = 'stock') -> Optional[Dict[str, dict]]:
    """
    从Redis获取实时价格
    
    Args:
        date: 日期 YYYYMMDD
        stock_codes: 股票代码列表
        table_type: 'stock' 或 'bond'
    
    Returns:
        {stock_code: {'price': x, 'change_pct': y, ...}} 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"
    
    # 获取最新时间戳
    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if not ts_data:
        return None
    
    timestamp = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    
    # 获取数据
    key = f"{table_name}:{timestamp}"
    df = load_dataframe_by_key(key)
    
    if df is None or df.empty:
        return None
    
    # 筛选指定股票
    df_filtered = df[df['stock_code'].isin(stock_codes)]
    
    # 转换为字典
    result = {}
    for _, row in df_filtered.iterrows():
        code = row['stock_code']
        result[code] = {
            'price': row.get('price', 0),
            'change_pct': float(row.get('change_pct', 0)) if pd.notna(row.get('change_pct')) else 0,
            'short_name': row.get('short_name', row.get('name', '')),
        }
    
    return result


def get_max_time_from_redis(date: str, table_type: str = 'stock') -> Optional[str]:
    """
    从Redis获取最新时间戳
    
    Args:
        date: 日期 YYYYMMDD
        table_type: 'stock' 或 'bond'
    
    Returns:
        时间字符串 HH:MM:SS 或 None
    """
    client = _get_redis_client()
    table_name = f"monitor_gp_sssj_{date}" if table_type == 'stock' else f"monitor_zq_sssj_{date}"
    
    ts_data = client.lindex(f"{table_name}:timestamps", 0)
    if ts_data:
        return ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
    return None
```

---

### 步骤3: 修改 stock_picker_service.py 使用Redis优先

**文件**: `src/gs2026/dashboard2/services/stock_picker_service.py`

#### 3.1 修改 `get_ztb_tags` 函数

```python
def get_ztb_tags(date: str = None) -> dict:
    """
    获取涨停行业概念标签（Redis优先）
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    today = datetime.now().strftime('%Y%m%d')
    
    # 【优化1】优先从Redis获取涨停股票
    zt_codes = None
    if date == today:
        try:
            zt_codes = redis_util.get_zt_stocks_from_redis(date, 'stock')
            if zt_codes:
                logger.info(f"从Redis获取涨停股票: {len(zt_codes)} 只")
        except Exception as e:
            logger.warning(f"Redis查询失败，回退到MySQL: {e}")
    
    # 【优化2】Redis无数据，回退到MySQL
    if not zt_codes:
        mysql_tool = mysql_util.get_mysql_tool()
        
        if date == today:
            # 当天：从实时监控表查
            try:
                with mysql_tool.engine.connect() as conn:
                    # 使用索引后的SQL
                    sql = f"SELECT DISTINCT stock_code FROM monitor_gp_sssj_{date} WHERE is_zt = 1"
                    rows = pd.read_sql(sql, conn).to_dict('records')
                    zt_codes = [r['stock_code'] for r in rows]
                    logger.info(f"从MySQL获取涨停股票: {len(zt_codes)} 只")
            except Exception as e:
                logger.warning(f"实时监控表查询失败({date}): {e}")
        
        if not zt_codes:
            # 历史日期：从涨停分析表查
            try:
                year = date[:4]
                table = f"analysis_ztb_detail_{year}"
                date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                with mysql_tool.engine.connect() as conn:
                    sql = f"SELECT DISTINCT stock_code FROM {table} WHERE trade_date = '{date_fmt}'"
                    rows = pd.read_sql(sql, conn).to_dict('records')
                    zt_codes = [r['stock_code'] for r in rows]
                    logger.info(f"从涨停分析表获取: {len(zt_codes)} 只")
            except Exception as e:
                logger.error(f"涨停分析表查询失败({date}): {e}")
    
    if not zt_codes:
        return {'date': date, 'total_zt': 0, 'industries': [], 'concepts': []}
    
    # 【步骤3-4】从宽表内存缓存获取行业和概念（不变）
    if not _stock_cache:
        load_memory_cache()
    
    industry_counter = defaultdict(int)
    concept_counter = defaultdict(int)
    
    for code in zt_codes:
        stock_data = _stock_cache.get(code)
        if stock_data:
            for ind in stock_data['industries']:
                industry_counter[ind] += 1
            for con in stock_data['concepts']:
                concept_counter[con] += 1
    
    # 构建名称→代码映射
    searcher = init_pinyin_searcher()
    name_to_code = {item['name']: item['code'] for item in searcher.items}
    
    # 排序并返回
    industries = sorted(
        [{'name': name, 'type': 'industry', 'code': name_to_code.get(name, ''), 'count': count}
         for name, count in industry_counter.items()],
        key=lambda x: x['count'], reverse=True
    )
    
    concepts = sorted(
        [{'name': name, 'type': 'concept', 'code': name_to_code.get(name, ''), 'count': count}
         for name, count in concept_counter.items()],
        key=lambda x: x['count'], reverse=True
    )
    
    return {
        'date': date,
        'total_zt': len(zt_codes),
        'industries': industries,
        'concepts': concepts
    }
```

#### 3.2 修改 `query_realtime_prices` 函数

```python
def query_realtime_prices(stock_codes: List[str], date: str = None) -> Dict[str, dict]:
    """
    查询实时价格（Redis优先）
    """
    if not stock_codes:
        return {}
    
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    # 【优化】优先从Redis获取
    try:
        result = redis_util.get_realtime_prices_from_redis(date, stock_codes, 'stock')
        if result:
            logger.debug(f"从Redis获取实时价格: {len(result)} 只")
            return result
    except Exception as e:
        logger.warning(f"Redis获取价格失败: {e}")
    
    # 【回退】从MySQL获取
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        
        # 【优化】使用Redis缓存的时间戳，避免子查询
        max_time = redis_util.get_max_time_from_redis(date, 'stock')
        
        with mysql_tool.engine.connect() as conn:
            if not max_time:
                # 如果Redis没有时间戳，查询MySQL
                time_row = pd.read_sql(
                    f"SELECT MAX(time) as max_time FROM monitor_gp_sssj_{date}",
                    conn
                ).to_dict('records')
                max_time = time_row[0]['max_time'] if time_row else None
            
            if not max_time:
                return {}
            
            placeholders = ','.join([f"'{code}'" for code in stock_codes])
            sql = f"""
                SELECT stock_code, short_name, price, change_pct 
                FROM monitor_gp_sssj_{date} 
                WHERE time = '{max_time}' AND stock_code IN ({placeholders})
            """
            
            rows = pd.read_sql(sql, conn).to_dict('records')
            
            return {row['stock_code']: {
                'price': row['price'],
                'change_pct': float(row['change_pct']) if row['change_pct'] else 0,
                'short_name': row['short_name']
            } for row in rows}
            
    except Exception as e:
        logger.error(f"查询实时价格失败: {e}")
        return {}
```

#### 3.3 修改 `query_bond_realtime_prices` 函数

```python
def query_bond_realtime_prices(bond_codes: List[str], date: str = None) -> Dict[str, dict]:
    """
    查询转债实时价格（Redis优先）
    """
    if not bond_codes:
        return {}
    
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    # 【优化】优先从Redis获取
    try:
        result = redis_util.get_realtime_prices_from_redis(date, bond_codes, 'bond')
        if result:
            logger.debug(f"从Redis获取转债价格: {len(result)} 只")
            return result
    except Exception as e:
        logger.warning(f"Redis获取转债价格失败: {e}")
    
    # 【回退】从MySQL获取（原逻辑）
    ...
```

---

### 步骤4: 在 monitor_stock.py 确保 is_zt 字段写入

**文件**: `src/gs2026/monitor/monitor_stock.py`

检查 `calc_is_zt` 函数是否正确计算并写入 `is_zt` 字段：

```python
# 确保在数据处理流程中调用 calc_is_zt
# 在 save_dataframe 之前，添加 is_zt 字段

def process_stock_data(df: pd.DataFrame) -> pd.DataFrame:
    """处理股票数据，添加 is_zt 字段"""
    # 计算是否涨停
    df['is_zt'] = df.apply(
        lambda row: calc_is_zt(row.get('change_pct'), row.get('code'), row.get('name')),
        axis=1
    )
    return df
```

---

## 四、完整优化流程图

### 4.1 涨停标签查询流程（优化后）

```
用户请求 /api/stock-picker/ztb-tags?date=20260423
    ↓
get_ztb_tags(date)
    ↓
【第一层: Redis查询】
    ├── 获取最新时间戳: monitor_gp_sssj_{date}:timestamps[0]
    ├── 获取数据: monitor_gp_sssj_{date}:{timestamp}
    ├── 内存筛选: df[df['is_zt'] == 1]
    └── 成功: 返回 zt_codes
    ↓ (Redis无数据)
【第二层: MySQL查询（带索引）】
    ├── SQL: SELECT DISTINCT stock_code FROM monitor_gp_sssj_{date} WHERE is_zt = 1
    ├── 使用索引: idx_is_zt
    └── 返回 zt_codes
    ↓
【第三层: 内存缓存查询】
    ├── 遍历 zt_codes
    ├── 从 _stock_cache 获取行业和概念
    └── 统计频次
    ↓
返回结果
```

### 4.2 实时价格查询流程（优化后）

```
query_realtime_prices(stock_codes)
    ↓
【第一层: Redis查询】
    ├── 获取最新时间戳: monitor_gp_sssj_{date}:timestamps[0]
    ├── 获取数据: monitor_gp_sssj_{date}:{timestamp}
    ├── 内存筛选: df[df['stock_code'].isin(stock_codes)]
    └── 成功: 返回价格数据
    ↓ (Redis无数据)
【第二层: MySQL查询（带索引）】
    ├── 获取时间戳: Redis缓存 或 MAX(time) 查询
    ├── SQL: SELECT ... WHERE time = '{max_time}' AND stock_code IN (...)
    ├── 使用索引: idx_time_code
    └── 返回价格数据
```

---

## 五、预期效果

### 5.1 性能对比

| 操作 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 涨停标签查询 | 2-5s (MySQL全表扫描) | <50ms (Redis内存) | **50-100x** |
| 实时价格查询 | 1-3s (MySQL子查询) | <30ms (Redis内存) | **30-100x** |
| 转债价格查询 | 1-3s (MySQL子查询) | <30ms (Redis内存) | **30-100x** |
| MySQL回退查询 | 2-5s (无索引) | <200ms (有索引) | **10-25x** |

### 5.2 架构优势

1. **Redis优先**: 99%的请求走Redis，毫秒级响应
2. **MySQL回退**: Redis无数据时自动回退，保证数据可用性
3. **索引保障**: MySQL查询使用索引，即使回退也能快速响应
4. **无单点故障**: Redis或MySQL任一故障，系统仍能工作

---

## 六、实施检查清单

### 6.1 代码修改清单

- [ ] 1. `table_index_manager.py`: 增加 is_zt 索引配置
- [ ] 2. `redis_util.py`: 增加 `get_zt_stocks_from_redis` 函数
- [ ] 3. `redis_util.py`: 增加 `get_realtime_prices_from_redis` 函数
- [ ] 4. `redis_util.py`: 增加 `get_max_time_from_redis` 函数
- [ ] 5. `stock_picker_service.py`: 修改 `get_ztb_tags` 使用Redis优先
- [ ] 6. `stock_picker_service.py`: 修改 `query_realtime_prices` 使用Redis优先
- [ ] 7. `stock_picker_service.py`: 修改 `query_bond_realtime_prices` 使用Redis优先
- [ ] 8. `monitor_stock.py`: 确保 `is_zt` 字段正确写入

### 6.2 数据库操作

- [ ] 为今日表添加索引: `monitor_gp_sssj_20260423`
- [ ] 为未来表自动添加索引（通过 table_index_manager）

### 6.3 测试验证

- [ ] Redis查询正常: `get_zt_stocks_from_redis('20260423')`
- [ ] MySQL回退正常: 停止Redis后查询仍能工作
- [ ] 性能测试: 对比优化前后查询耗时

---

## 七、风险与应对

| 风险 | 可能性 | 应对措施 |
|------|--------|----------|
| Redis数据不一致 | 低 | 设置过期时间，定期从MySQL刷新 |
| is_zt 字段未写入 | 中 | 检查 monitor_stock.py 数据处理流程 |
| 索引添加失败 | 低 | 检查表是否存在，错误日志监控 |
| Redis连接失败 | 低 | 自动回退到MySQL，保证可用性 |

---

## 八、文档位置

`docs/07-系统维护/涨停行概选股性能优化方案-v2-Redis优先.md`

---

**方案状态**: 待审核
**推荐实施**: 审核通过后立即实施
**预期收益**: 查询性能提升 50-100倍
