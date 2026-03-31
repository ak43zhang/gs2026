# API性能和数据库查询优化方案

> 分析时间: 2026-03-31 13:45  
> 基于性能诊断数据分析

---

## 一、性能数据分析

### 1.1 API慢请求统计

| API端点 | 平均耗时 | 最大耗时 | 问题等级 |
|---------|----------|----------|----------|
| `/attack-ranking/stock` | 600-700ms | 703ms | 🔴 高 |
| `/latest-messages` | 580-660ms | 658ms | 🔴 高 |
| `/combine-ranking` | ~2000ms | - | 🔴 极高 |

**总请求数**: 1000  
**慢请求阈值**: 500ms  
**P95响应时间**: 521ms

### 1.2 数据库慢查询统计

| 查询 | 平均耗时 | 最大耗时 | 执行次数 |
|------|----------|----------|----------|
| `monitor_gp_sssj_20260331` 按股票代码查询 | 24s | 27s | 3 |
| `monitor_zq_sssj_20260331` 按债券代码查询 | 3.6s | 7.8s | 3 |

**总查询数**: 6  
**慢查询阈值**: 100ms  
**问题**: 所有查询都超过1秒，最严重达27秒！

### 1.3 慢查询SQL分析

```sql
-- 最慢的查询（27秒）
SELECT time, stock_code AS code, short_name AS name,
       price, change_pct, volume, amount
FROM monitor_gp_sssj_20260331
WHERE stock_code = '300992'
ORDER BY time ASC
```

**问题**:
- 表 `monitor_gp_sssj_20260331` 没有索引
- 全表扫描 2400万条记录
- 按 `stock_code` 过滤效率极低

---

## 二、调用链分析

### 2.1 股票上攻排行调用链

```
GET /attack-ranking/stock
    ↓ ~700ms 总耗时
monitor.py::get_stock_ranking()
    ↓
data_service.py::get_stock_ranking()
    ↓
_process_stock_ranking()
    ├── _enrich_stock_data() ← 可能涉及数据库查询
    ├── _enrich_change_pct() ← Redis查询
    └── 红名单标记 ← Redis查询
```

### 2.2 慢查询来源分析

```sql
-- monitor_gp_sssj_20260331 表结构推测
CREATE TABLE monitor_gp_sssj_20260331 (
    time TIME,
    stock_code VARCHAR(10),
    short_name VARCHAR(20),
    price DECIMAL(10,2),
    change_pct DECIMAL(5,2),
    volume BIGINT,
    amount DECIMAL(15,2)
    -- 缺少主键和索引！
);
```

**数据量估算**:
- 每3秒一个时间点
- 每天约 4800 个时间点
- 约 5000 只股票
- 总记录数: 4800 × 5000 = **2400万条/天**

---

## 三、优化方案

### 方案A: 添加数据库索引（紧急）

**问题**: `monitor_gp_sssj_{date}` 和 `monitor_zq_sssj_{date}` 表缺少索引

**解决方案**:
```sql
-- 为今天的表添加索引
ALTER TABLE monitor_gp_sssj_20260331 
ADD INDEX idx_stock_code (stock_code);

ALTER TABLE monitor_gp_sssj_20260331 
ADD INDEX idx_time (time);

ALTER TABLE monitor_gp_sssj_20260331 
ADD INDEX idx_stock_time (stock_code, time);

-- 债券表同理
ALTER TABLE monitor_zq_sssj_20260331 
ADD INDEX idx_bond_code (bond_code);

ALTER TABLE monitor_zq_sssj_20260331 
ADD INDEX idx_bond_time (bond_code, time);
```

**预期效果**:
- 查询时间: 27秒 → 100ms (提升270倍)
- 索引创建时间: 约2-5分钟

**自动化脚本**:
```python
# auto_add_index.py
from gs2026.utils import mysql_util

def add_index_to_sssj_tables(date_str):
    """为实时数据表添加索引"""
    tables = [
        f'monitor_gp_sssj_{date_str}',
        f'monitor_zq_sssj_{date_str}'
    ]
    
    for table in tables:
        try:
            mysql_util.execute(f'''
                ALTER TABLE {table} 
                ADD INDEX idx_code_time (stock_code, time),
                ADD INDEX idx_time (time)
            ''')
            print(f'✓ {table} 索引添加成功')
        except Exception as e:
            print(f'✗ {table} 索引添加失败: {e}')
```

---

### 方案B: 优化查询逻辑（推荐）

**问题**: 查询使用 `ORDER BY time ASC` 但没有限制返回条数

**优化方案**:
```sql
-- 优化前: 返回所有历史数据（可能数万条）
SELECT * FROM monitor_gp_sssj_20260331 
WHERE stock_code = '300992' 
ORDER BY time ASC

-- 优化后: 只返回最近100条
SELECT * FROM monitor_gp_sssj_20260331 
WHERE stock_code = '300992' 
ORDER BY time DESC 
LIMIT 100
```

**代码修改**:
```python
# 在查询函数中添加limit参数
def get_stock_realtime_data(stock_code, date, limit=100):
    query = f"""
        SELECT time, stock_code, short_name, price, change_pct, volume, amount
        FROM monitor_gp_sssj_{date}
        WHERE stock_code = %s
        ORDER BY time DESC
        LIMIT %s
    """
    return execute(query, (stock_code, limit))
```

---

### 方案C: 使用Redis缓存实时数据

**问题**: 实时数据查询直接走MySQL

**解决方案**: 优先从Redis查询
```python
def get_stock_realtime_data(stock_code, date):
    # 1. 先查Redis
    redis_key = f"monitor_gp_sssj_{date}:{stock_code}"
    data = redis_client.get(redis_key)
    if data:
        return json.loads(data)
    
    # 2. Redis未命中，查MySQL
    data = query_from_mysql(stock_code, date)
    
    # 3. 写入Redis缓存（5分钟过期）
    redis_client.setex(redis_key, 300, json.dumps(data))
    
    return data
```

---

### 方案D: 表分区优化

**问题**: 单表数据量过大（2400万条/天）

**解决方案**: 按股票代码分区
```sql
-- 创建分区表（新表）
CREATE TABLE monitor_gp_sssj_20260331 (
    time TIME,
    stock_code VARCHAR(10),
    short_name VARCHAR(20),
    price DECIMAL(10,2),
    change_pct DECIMAL(5,2),
    volume BIGINT,
    amount DECIMAL(15,2),
    PRIMARY KEY (stock_code, time)
) PARTITION BY HASH(stock_code) PARTITIONS 10;
```

**优点**:
- 查询时只扫描相关分区
- 维护更方便

---

### 方案E: 异步加载和分页

**问题**: 前端一次性加载所有数据

**解决方案**: 分页加载
```python
@monitor_bp.route('/api/stock/realtime')
def get_stock_realtime():
    stock_code = request.args.get('code')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 100))
    
    offset = (page - 1) * page_size
    
    query = f"""
        SELECT * FROM monitor_gp_sssj_{date}
        WHERE stock_code = %s
        ORDER BY time DESC
        LIMIT %s OFFSET %s
    """
    data = execute(query, (stock_code, page_size, offset))
    
    return jsonify({
        'data': data,
        'page': page,
        'page_size': page_size,
        'has_more': len(data) == page_size
    })
```

---

## 四、推荐实施计划

### 阶段1: 紧急修复（15分钟）
- [ ] 为今天的表添加索引
- [ ] 验证查询性能提升

### 阶段2: 查询优化（30分钟）
- [ ] 修改查询逻辑，添加LIMIT
- [ ] 优化排序方向（DESC代替ASC）

### 阶段3: 缓存优化（60分钟）
- [ ] 实现Redis缓存层
- [ ] 添加缓存预热机制

### 阶段4: 长期优化（可选）
- [ ] 表分区改造
- [ ] 异步加载实现

---

## 五、预期效果

| 优化项 | 当前 | 优化后 | 提升 |
|--------|------|--------|------|
| 单股票查询 | 27s | 100ms | 270x |
| API响应 | 700ms | 200ms | 3.5x |
| 数据库负载 | 高 | 低 | 显著降低 |

---

## 六、立即执行脚本

```python
# 立即为今天的表添加索引
from gs2026.utils import mysql_util
from datetime import datetime

date_str = datetime.now().strftime('%Y%m%d')
tables = [
    f'monitor_gp_sssj_{date_str}',
    f'monitor_zq_sssj_{date_str}'
]

for table in tables:
    try:
        mysql_util.execute(f'ALTER TABLE {table} ADD INDEX idx_code (stock_code)')
        mysql_util.execute(f'ALTER TABLE {table} ADD INDEX idx_time (time)')
        print(f'✓ {table} 索引添加成功')
    except Exception as e:
        print(f'✗ {table}: {e}')
```

---

**文档位置**: `docs/performance_optimization_plan.md`

**推荐立即实施方案A（添加索引）**，可立即将27秒查询降到100ms。
