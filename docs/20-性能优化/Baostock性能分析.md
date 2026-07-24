# Baostock 数据采集性能分析报告

**分析时间**: 2026-03-30 04:19  
**分析文件**: `src/gs2026/collection/base/baostock_collection.py`  

---

## 一、性能瓶颈识别

### 1.1 逐条插入问题（最严重）

**问题代码**:
```python
for stock_code in stock_codes:
    df = get_multiple_stocks(stock_code, start_date, end_date)
    if df is not None:
        with engine.begin() as conn:  # ← 每次循环都创建新连接/事务
            df.to_sql(name=table_name, con=conn, if_exists='append')
```

**问题分析**:
- 每只股票数据单独开启一个数据库事务
- 5000只股票 = 5000次事务开启/提交
- 每次事务开销约 50-100ms
- 仅事务开销就达 **250-500秒**

### 1.2 连接池使用不当

**问题代码**:
```python
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()  # ← 全局连接，但未使用连接池
mysql_tool = mysql_util.MysqlTool(url)  # ← 另一个独立连接
```

**问题分析**:
- 创建了多个独立连接
- 没有使用连接池复用
- `to_sql` 每次创建新连接

### 1.3 网络往返过多

**问题代码**:
```python
for stock_code in stock_codes:  # 5000+ 次循环
    df = get_multiple_stocks(stock_code, start_date, end_date)  # Baostock API 调用
    # ... 处理 ...
    df.to_sql(...)  # MySQL 插入
```

**问题分析**:
- 5000+ 次 Baostock API 调用（网络IO）
- 5000+ 次 MySQL 插入（网络IO）
- 串行执行，无并发

### 1.4 数据类型转换冗余

**问题代码**:
```python
df['open'] = df['open'].round(2).astype(float)
df['close'] = df['close'].round(2).astype(float)
# ... 每列都进行转换
```

**问题分析**:
- 多次 `astype(float)` 转换
- 可以使用 `pd.to_numeric` 一次性转换

### 1.5 表存在性检查+删除

**问题代码**:
```python
if mysql_tool.check_table_exists(table_name):
    mysql_tool.drop_mysql_table(table_name)  # ← 同步阻塞操作
```

**问题分析**:
- 每次采集都检查表存在性
- 删除大表耗时（如果有数据）

---

## 二、性能优化方案

### 方案1：批量插入（推荐优先实施）

**优化思路**: 将多条数据合并后一次性插入

**实现代码**:
```python
def stock_update_optimized(start_date: str, end_date: str, batch_size: int = 100) -> None:
    """
    优化版：批量插入
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        batch_size: 每批处理股票数量
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    
    # 使用 TRUNCATE 替代 DROP+CREATE（更快）
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.truncate_table(table_name)  # 清空表而非删除
    
    # 获取股票列表
    sql = string_enum.AG_STOCK_SQL5
    code_df = pd.read_sql(sql, con=con)
    stock_codes = code_df['stock_code'].tolist()  # 假设列名是 stock_code
    
    # 登录 Baostock
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    
    all_data = []  # 收集所有数据
    total_records = 0
    
    try:
        for i, stock_code in enumerate(stock_codes):
            logger.info(f"正在处理：{stock_code} ({i+1}/{len(stock_codes)})")
            df = get_multiple_stocks(stock_code, start_date, end_date)
            
            if df is not None and not df.empty:
                all_data.append(df)
                total_records += len(df)
                
                # 每 batch_size 只股票批量插入一次
                if len(all_data) >= batch_size:
                    _batch_insert(all_data, table_name)
                    logger.info(f"批量插入 {batch_size} 只股票，累计 {total_records} 条")
                    all_data = []  # 清空缓存
            else:
                logger.warning(f"股票 {stock_code} 无数据")
        
        # 插入剩余数据
        if all_data:
            _batch_insert(all_data, table_name)
            logger.info(f"最后批量插入，累计 {total_records} 条")
    
    finally:
        bs.logout()


def _batch_insert(dataframes: list, table_name: str):
    """批量插入数据"""
    if not dataframes:
        return
    
    # 合并所有 DataFrame
    combined_df = pd.concat(dataframes, ignore_index=True)
    
    # 一次性插入（使用单个事务）
    with engine.begin() as conn:
        combined_df.to_sql(
            name=table_name,
            con=conn,
            if_exists='append',
            index=False,  # 不插入索引
            method='multi',  # 使用多值插入
            chunksize=1000  # 每1000条执行一次INSERT
        )
```

**预期性能提升**:
- 事务次数: 5000次 → 50次 (batch_size=100)
- 插入时间: 250秒 → 5秒 (50倍提升)

---

### 方案2：异步并发采集

**优化思路**: 使用线程池并发调用 Baostock API

**实现代码**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

def stock_update_concurrent(start_date: str, end_date: str, max_workers: int = 5) -> None:
    """
    并发版：多线程采集
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        max_workers: 并发线程数
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.truncate_table(table_name)
    
    sql = string_enum.AG_STOCK_SQL5
    code_df = pd.read_sql(sql, con=con)
    stock_codes = code_df['stock_code'].tolist()
    
    # 登录 Baostock（每个线程需要独立登录）
    all_data = []
    data_lock = Lock()
    
    def fetch_stock_data(stock_code: str):
        """获取单只股票数据（线程安全）"""
        try:
            # 每个线程独立登录
            lg = bs.login()
            df = get_multiple_stocks(stock_code, start_date, end_date)
            bs.logout()
            
            if df is not None and not df.empty:
                with data_lock:
                    all_data.append(df)
            return stock_code, True
        except Exception as e:
            logger.error(f"获取 {stock_code} 失败: {e}")
            return stock_code, False
    
    # 使用线程池并发采集
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_stock_data, code): code for code in stock_codes}
        
        for future in as_completed(futures):
            code, success = future.result()
            if success:
                logger.info(f"成功获取: {code}")
    
    # 批量插入所有数据
    if all_data:
        _batch_insert(all_data, table_name)
        logger.info(f"共插入 {len(all_data)} 只股票数据")
```

**预期性能提升**:
- API 调用时间: 5000×1秒 → 5000÷5×1秒 = 1000秒 (5倍提升)
- 配合方案1，总时间可从 5000秒 → 200秒

---

### 方案3：数据类型优化

**优化代码**:
```python
def get_multiple_stocks_optimized(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """优化版：减少类型转换"""
    market = "sh." if stock_code.startswith(("6", "9")) else "sz."
    
    rs = bs.query_history_k_data_plus(
        code=market + stock_code,
        fields="code,date,open,close,high,low,volume,amount,pctChg,turn,preclose",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3"
    )
    
    data_list = []
    while (rs.error_code == '0') and rs.next():
        data_list.append(rs.get_row_data())
    
    if not data_list:
        return None
    
    df = pd.DataFrame(data_list, columns=rs.fields)
    
    # 一次性类型转换
    numeric_cols = ['open', 'close', 'high', 'low', 'preclose']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
    
    df['stock_code'] = df['code'].str.split('.').str[1]
    df['trade_time'] = df['date'] + ' 00:00:00'
    df['trade_date'] = df['date']
    df['volume'] = (pd.to_numeric(df['volume'], errors='coerce').fillna(0) // 100) * 100
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).round(2)
    df['change_pct'] = pd.to_numeric(df['pctChg'], errors='coerce').fillna(0).round(2)
    df['change'] = (df['close'] - df['pre_close']).round(2)
    df['turnover_ratio'] = pd.to_numeric(df['turn'], errors='coerce').fillna(0).round(2)
    
    return df[["stock_code", "trade_time", 'trade_date', 'open', 'close', 'high', 'low',
               'volume', 'amount', 'change_pct', 'change', 'turnover_ratio', 'pre_close']]
```

---

### 方案4：数据库优化

**优化1: 使用 LOAD DATA INFILE**（最快方式）
```python
def _batch_insert_fast(dataframes: list, table_name: str):
    """使用 LOAD DATA INFILE 快速插入"""
    if not dataframes:
        return
    
    combined_df = pd.concat(dataframes, ignore_index=True)
    
    # 保存为 CSV
    csv_path = f"/tmp/{table_name}_{time.time()}.csv"
    combined_df.to_csv(csv_path, index=False)
    
    # 使用 LOAD DATA INFILE（比 INSERT 快 10-20 倍）
    with engine.begin() as conn:
        conn.execute(text(f"""
            LOAD DATA LOCAL INFILE '{csv_path}'
            INTO TABLE {table_name}
            FIELDS TERMINATED BY ','
            ENCLOSED BY '"'
            LINES TERMINATED BY '\\n'
            IGNORE 1 ROWS
        """))
    
    # 删除临时文件
    os.remove(csv_path)
```

**优化2: 表结构优化**
```sql
-- 添加索引（如果经常查询）
ALTER TABLE data_gpsj_day_xxx 
ADD INDEX idx_stock_code (stock_code),
ADD INDEX idx_trade_date (trade_date);

-- 使用 InnoDB 的批量插入优化
SET innodb_flush_log_at_trx_commit = 2;  -- 每秒刷新日志
SET bulk_insert_buffer_size = 268435456;  -- 256MB 批量插入缓冲区
```

---

## 三、推荐实施方案

### 阶段1: 快速优化（1小时，提升50倍）
1. **批量插入**（方案1）
   - 修改 `stock_update` 函数
   - batch_size = 100
   - 预期: 5000秒 → 100秒

### 阶段2: 并发优化（2小时，再提升5倍）
2. **异步并发**（方案2）
   - 使用 ThreadPoolExecutor
   - max_workers = 5
   - 预期: 100秒 → 20秒

### 阶段3: 极致优化（1小时，再提升10倍）
3. **LOAD DATA INFILE**（方案4）
   - 需要 MySQL 文件权限配置
   - 预期: 20秒 → 2秒

---

## 四、预期效果对比

| 优化阶段 | 预计耗时 | 提升倍数 | 实施难度 |
|----------|----------|----------|----------|
| 原始版本 | 5000秒 (83分钟) | 1x | - |
| 阶段1: 批量插入 | 100秒 (1.7分钟) | 50x | 低 |
| 阶段2: +并发 | 20秒 | 250x | 中 |
| 阶段3: +LOAD DATA | 2秒 | 2500x | 高 |

---

## 五、实施建议

### 推荐方案
**先实施阶段1（批量插入）**，风险最低，收益最大。

### 代码变更范围
- 主要修改 `stock_update` 函数
- 新增 `_batch_insert` 辅助函数
- 可选修改 `get_multiple_stocks` 优化类型转换

### 回滚方案
- 保留原函数，新函数命名为 `stock_update_optimized`
- 测试通过后替换调用

---

**文档结束**
