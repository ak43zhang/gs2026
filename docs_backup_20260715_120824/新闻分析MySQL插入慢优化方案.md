# 新闻分析MySQL插入慢优化方案

## 问题分析

### 当前流程

```
deepseek_ai分析完成
    ↓
① 标记原始表已分析（UPDATE）
② 插入分析结果JSON（INSERT）
    ↓
process_batch拆分入库
    ↓
逐条处理（15-20条）
    ↓
每条：extract_record → save_to_mysql → save_to_redis
    ↓
MySQL：单条INSERT ON DUPLICATE KEY UPDATE（15-20次）
Redis：pipeline批量（1次）
```

### 性能瓶颈

**瓶颈1：MySQL单条插入（最大问题）**
```python
# 当前：逐条插入，每条都执行SQL
for msg in messages:  # 15-20条
    record = extract_record(msg, ...)
    save_to_mysql(record)  # 每条执行1次INSERT
```
问题：
- 15-20条消息 = 15-20次INSERT
- 每次INSERT都是独立的数据库操作
- 网络往返 + 事务开销 = 慢

**瓶颈2：连接管理**
```python
def save_to_mysql(record):
    mysql_tool.update_data(sql)  # 每次新建连接
```
问题：
- 每条记录都新建数据库连接
- 连接建立/断开开销大

**瓶颈3：SQL拼接**
```python
sql = f"""INSERT INTO analysis_news_detail_2026 ...
    VALUES (...)
    ON DUPLICATE KEY UPDATE ..."""
```
问题：
- 单条SQL字符串拼接
- 无法利用批量插入优化

## 优化方案

### 方案A：批量插入（推荐）

**核心思路：** 多条记录合并为1条INSERT

```python
def save_to_mysql_batch(records: List[Dict]) -> bool:
    """批量插入多条记录"""
    if not records:
        return False
    
    try:
        # 构建批量VALUES
        values_list = []
        for record in records:
            def esc(val):
                if val is None:
                    return 'NULL'
                s = str(val).replace("'", "\\'").replace("\\", "\\\\")
                return f"'{s}'"
            
            publish_time_sql = esc(record['publish_time']) if record['publish_time'] else 'NULL'
            
            value_tuple = f"""({esc(record['content_hash'])}, {esc(record['source_table'])},
                {esc(record['title'])}, {esc(record['content'])},
                {publish_time_sql}, {esc(record['source'])},
                {record['importance_score']}, {record['business_impact_score']}, {record['composite_score']},
                {esc(record['news_size'])}, {esc(record['news_type'])},
                {esc(record['sectors'])}, {esc(record['concepts'])},
                {esc(record['leading_stocks'])}, {esc(record['sector_details'])},
                {esc(record['deep_analysis'])},
                {esc(record['analysis_version'])}, NOW())"""
            values_list.append(value_tuple)
        
        # 批量INSERT
        values_str = ',\n'.join(values_list)
        sql = f"""INSERT INTO analysis_news_detail_2026 
            (content_hash, source_table, title, content, publish_time, source,
             importance_score, business_impact_score, composite_score,
             news_size, news_type, sectors, concepts, leading_stocks, sector_details,
             deep_analysis, analysis_time, analysis_version)
            VALUES {values_str}
            ON DUPLICATE KEY UPDATE
                importance_score = VALUES(importance_score),
                business_impact_score = VALUES(business_impact_score),
                composite_score = VALUES(composite_score),
                news_size = VALUES(news_size),
                news_type = VALUES(news_type),
                sectors = VALUES(sectors),
                concepts = VALUES(concepts),
                leading_stocks = VALUES(leading_stocks),
                sector_details = VALUES(sector_details),
                deep_analysis = VALUES(deep_analysis),
                analysis_time = VALUES(analysis_time),
                analysis_version = VALUES(analysis_version)"""
        
        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"批量MySQL写入失败: {e}")
        return False
```

**修改process_batch：**
```python
def process_batch(json_data: str, source_table: str, version: str) -> Dict[str, int]:
    # ... 解析JSON ...
    
    records = []
    for msg in messages:
        record = extract_record(msg, source_table, version)
        if record:
            records.append(record)
    
    # 【优化】批量插入MySQL
    if records:
        if save_to_mysql_batch(records):  # 1次批量插入
            stats['mysql_ok'] = len(records)
        else:
            stats['failed'] = len(records)
    
    # Redis保持逐条（已有pipeline优化）
    for record in records:
        if save_to_redis(record):
            stats['redis_ok'] += 1
```

**预期性能提升：**
- 当前：15-20次INSERT = 15-20次网络往返
- 优化：1次批量INSERT = 1次网络往返
- 提升：15-20倍

### 方案B：连接池复用

**问题：** `update_data`每次新建连接

**优化：** 使用SQLAlchemy连接池
```python
# 已有engine，直接使用
with engine.begin() as conn:
    conn.execute(text(sql))
```

### 方案C：异步写入

**思路：** MySQL和Redis并行执行
```python
import asyncio

async def save_async(record):
    mysql_task = asyncio.create_task(save_to_mysql_async(record))
    redis_task = asyncio.create_task(save_to_redis_async(record))
    await asyncio.gather(mysql_task, redis_task)
```

## 推荐方案

**方案A（批量插入）+ 方案B（连接池）**

理由：
1. 批量插入是最大瓶颈，优化效果最明显
2. 连接池复用减少连接建立开销
3. 改动范围小，风险可控

## 实施步骤

1. 新增`save_to_mysql_batch`函数（批量插入）
2. 修改`process_batch`使用批量插入
3. 修改`save_to_mysql`使用SQLAlchemy连接池
4. 测试验证

## 预期效果

| 指标 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| MySQL插入次数 | 15-20次 | 1次 | 15-20x |
| 网络往返 | 15-20次 | 1次 | 15-20x |
| 总耗时 | ~3-5秒 | ~0.2-0.5秒 | 6-10x |

---

等待用户确认后实施。
