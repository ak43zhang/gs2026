# 股票 vs 债券区间次数完整对比分析与修复方案

## 一、股票 vs 债券完整差异对比

### 1.1 入口函数差异

| 对比项 | 股票 `get_stock_ranking` | 债券 `get_bond_ranking` | 差异说明 |
|--------|------------------------|------------------------|---------|
| 行号 | 1709 | 1982 | - |
| `actual_date` 生成 | `date or datetime.now().strftime('%Y%m%d')` | 相同 | 两者都可能带横线 |
| 时间轴模式处理 | `if time_str:` 内完成所有操作 | `if time_str:` 只调 `_get_ranking_fast` | **债券在 `if` 外调 `_enrich_bond_data`** |
| `_enrich_*_data` 调用位置 | `if time_str:` 块内（行1725） | `if time_str:` 块外（行2006） | **债券 `time_str` 可能为 None** |
| 实时模式 `time_str` | `datetime.now().strftime("%H:%M:%S")`（行1909） | 未传入（保持 None） | **债券实时模式无 time_str** |

### 1.2 数据 enrichment 差异

| 对比项 | 股票 `_enrich_stock_data` | 债券 `_enrich_bond_data` | 差异说明 |
|--------|--------------------------|-------------------------|---------|
| 行号 | 445 | 1075 | - |
| `window_count` 查询条件 | `if date and time_str:`（行455） | 无条件，直接查询（行1177） | **债券可能用 `query_time` 而非 `time_str`** |
| `window_count` 默认值 | 显式设为 0（行458-459） | 从 `_get_bond_window_count_batch` 获取 | **债券依赖函数返回值** |
| 异常处理 | `window_count` 设为 0（行464-466） | 无显式处理 | **债券异常时可能无 `window_count` 字段** |

### 1.3 `_get_*_window_count_batch` 差异

| 对比项 | 股票 `_get_stock_window_count_batch` | 债券 `_get_bond_window_count_batch` | 差异说明 |
|--------|-------------------------------------|------------------------------------|---------|
| 行号 | 1042 | 982 | - |
| 表名生成 | `f"monitor_gp_top30_{date}"` | `f"monitor_zq_top30_{date}"` | 前缀不同（gp vs zq） |
| `date` 处理 | 直接使用 | 直接使用 | **两者都可能带横线** |
| `window_start` 计算 | 相同 | 相同 | 都是10分钟区间 |
| SQL 逻辑 | 相同 | 相同 | 都是取当前区间最新记录 |
| 无记录返回值 | 0 | 0 | 相同 |

### 1.4 关键差异总结

**差异1：`actual_date` 格式不一致**
- 两者都使用 `date or datetime.now().strftime('%Y%m%d')`
- 如果前端传 `date='2026-07-31'`，`actual_date='2026-07-31'`（带横线）
- `_get_ranking_fast` 内部用 `date.replace('-', '')` 处理
- `_get_*_window_count_batch` 直接用 `date`，表名错误

**差异2：债券 `_enrich_bond_data` 中 `time_str` 可能为 None**
- 股票：只在 `if time_str:` 块内调用 `_enrich_stock_data`，`time_str` 一定存在
- 债券：在 `if time_str:` 块外调用 `_enrich_bond_data`，实时模式下 `time_str=None`

**差异3：债券 `query_time` 确定逻辑**
- 股票：直接使用传入的 `time_str`
- 债券：如果 `time_str` 为 None，从 Redis 获取最新时间戳

**差异4：异常处理**
- 股票：异常时显式设置 `window_count = 0`
- 债券：异常时可能不设置 `window_count` 字段

## 二、根因确认

### 2.1 表名格式问题（主要根因）

```python
# _get_bond_window_count_batch 中
table_name = f"monitor_zq_top30_{date}"
# 如果 date='2026-07-31'，表名 = "monitor_zq_top30_2026-07-31"（错误！）
# 正确表名 = "monitor_zq_top30_20260731"
```

### 2.2 time_str 传递问题（次要根因）

```python
# get_bond_ranking 中
if time_str:
    data = _get_ranking_fast('bond', actual_date, time_str, limit)
# elif ...
else:
    use_mysql = True
    data = data_service.get_bond_ranking(...)  # time_str 仍为 None

data = _enrich_bond_data(data, actual_date, time_str)  # 可能传入 None
```

### 2.3 数据写入流程

**股票/债券 `window_count` 写入**：
- 由 `monitor_stock.py` 调用 `get_window_count()` 计算
- 写入 `monitor_gp_top30_{date}` / `monitor_zq_top30_{date}` 表的 `window_count` 字段
- 使用10分钟区间（已改造完成）

## 三、数据重新填充方案

### 3.1 检查当前数据状态

```sql
-- 检查今日债券表是否存在
SHOW TABLES LIKE 'monitor_zq_top30_20260731';

-- 检查表结构
DESCRIBE monitor_zq_top30_20260731;

-- 检查window_count字段是否存在
SELECT COLUMN_NAME 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'monitor_zq_top30_20260731' 
AND COLUMN_NAME = 'window_count';

-- 检查数据分布（按区间）
SELECT 
    SUBSTRING(time, 1, 5) as hour_minute,
    COUNT(*) as tick_count,
    AVG(window_count) as avg_wc,
    MAX(window_count) as max_wc
FROM monitor_zq_top30_20260731
GROUP BY SUBSTRING(time, 1, 5)
ORDER BY hour_minute;
```

### 3.2 数据重新填充脚本

**方案A：从Redis重新计算（推荐）**

```python
# _recalc_bond_window_count.py
"""
重新计算债券window_count并填充MySQL
从Redis读取历史tick数据，按10分钟区间重新计算
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from datetime import datetime
from gs2026.utils import redis_util, config_util
from sqlalchemy import create_engine, text
import pandas as pd

def recalc_bond_window_count(date_str: str):
    """
    重新计算债券window_count
    
    Args:
        date_str: 日期 YYYYMMDD
    """
    # 连接Redis
    client = redis_util._get_redis_client()
    
    # 连接MySQL
    url = config_util.get_config('common.url')
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    # 获取所有tick时间戳
    ts_key = f"monitor_zq_sssj_{date_str}:timestamps"
    timestamps = client.lrange(ts_key, 0, -1)
    if not timestamps:
        print(f"Redis中没有 {date_str} 的时间戳数据")
        return
    
    timestamps = [ts.decode('utf-8') if isinstance(ts, bytes) else ts for ts in timestamps]
    timestamps.sort()
    print(f"找到 {len(timestamps)} 个tick时间点")
    
    # 按区间累计
    window_counts = {}  # {(window_start, code): count}
    
    table_name = f"monitor_zq_top30_{date_str}"
    
    with engine.connect() as conn:
        for time_str in timestamps:
            # 计算当前区间起始
            hh, mm, _ = time_str.split(':')
            window_start = f"{hh}:{(int(mm)//10)*10:02d}:00"
            
            # 获取该tick的债券列表
            tick_key = f"monitor_zq_top30_{date_str}:{time_str}"
            tick_data = client.hgetall(tick_key)
            
            if not tick_data:
                continue
            
            # 更新区间次数
            for code_bytes in tick_data.keys():
                code = code_bytes.decode('utf-8') if isinstance(code_bytes, bytes) else code_bytes
                key = (window_start, code)
                
                if key not in window_counts:
                    window_counts[key] = 0
                window_counts[key] += 1
                
                # 更新MySQL
                sql = text(f"""
                    UPDATE {table_name}
                    SET window_count = :wc
                    WHERE code = :code AND time = :time
                """)
                conn.execute(sql, {
                    'wc': window_counts[key],
                    'code': code,
                    'time': time_str
                })
        
        conn.commit()
    
    print(f"完成 {len(window_counts)} 条记录的window_count更新")

if __name__ == '__main__':
    today = datetime.now().strftime('%Y%m%d')
    recalc_bond_window_count(today)
```

**方案B：SQL窗口函数批量更新（更快）**

```sql
-- _recalc_bond_wc_10min.sql
-- 使用窗口函数按10分钟区间重新计算window_count

UPDATE monitor_zq_top30_{date} t1
JOIN (
    SELECT 
        code,
        time,
        -- 计算10分钟区间起始
        CONCAT(
            SUBSTRING(time, 1, 3),
            LPAD(FLOOR(SUBSTRING(time, 4, 2) / 10) * 10, 2, '0'),
            ':00'
        ) as window_start,
        -- 区间内累计次数
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 3), LPAD(FLOOR(SUBSTRING(time, 4, 2) / 10) * 10, 2, '0'), ':00')
            ORDER BY time
        ) as rn
    FROM monitor_zq_top30_{date}
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.rn;
```

## 四、代码修复方案

### 4.1 修复1：统一 date 格式（无横线）

**修改 `get_bond_ranking`**（行1985）：
```python
# 原代码
actual_date = date or datetime.now().strftime('%Y%m%d')

# 修改为
actual_date = (date or datetime.now().strftime('%Y%m%d')).replace('-', '')
```

**同样修改 `get_stock_ranking`**（行1712）：
```python
actual_date = (date or datetime.now().strftime('%Y%m%d')).replace('-', '')
```

### 4.2 修复2：确保债券 time_str 正确传递

**修改 `get_bond_ranking`**（行1999-2007）：
```python
# 原代码
if time_str:
    data = _get_ranking_fast('bond', actual_date, time_str, limit)
elif date and _is_historical(date):
    time_str = '15:00:00'
    data = _get_ranking_fast('bond', date, time_str, limit)
else:
    use_mysql = True
    data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)

data = _enrich_bond_data(data, actual_date, time_str)

# 修改为
if time_str:
    query_time = time_str
    data = _get_ranking_fast('bond', actual_date, time_str, limit)
elif date and _is_historical(date):
    query_time = '15:00:00'
    data = _get_ranking_fast('bond', date, query_time, limit)
else:
    # 实时模式：使用当前时间
    query_time = datetime.now().strftime('%H:%M:%S')
    use_mysql = True
    data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)

data = _enrich_bond_data(data, actual_date, query_time)
```

### 4.3 修复3：债券异常处理增强

**修改 `_enrich_bond_data`**（行1177-1180）：
```python
# 在 try 块内添加
window_count_map = _get_bond_window_count_batch(date, query_time, bond_codes)

# 填充数据
for bond in bonds:
    code = bond.get('code', '')
    # ... 其他字段 ...
    bond['window_count'] = window_count_map.get(code, 0)  # 默认0

# 在 except 块内添加
except Exception as e:
    print(f"添加债券信息失败: {e}")
    for bond in bonds:
        bond['window_count'] = 0  # 异常时默认0
    return bonds
```

## 五、验证方案

### 5.1 数据验证

```sql
-- 验证09:40:00区间的window_count从1开始
SELECT code, time, window_count
FROM monitor_zq_top30_20260731
WHERE time >= '09:40:00' AND time < '09:41:00'
ORDER BY code, time
LIMIT 10;

-- 验证09:40:00第一笔的window_count=1
SELECT code, MIN(time) as first_time, window_count
FROM monitor_zq_top30_20260731
WHERE time >= '09:40:00' AND time < '09:50:00'
GROUP BY code
HAVING first_time = MIN(first_time)
ORDER BY code
LIMIT 10;
```

### 5.2 功能验证

1. 前端选择09:40:00
2. 检查债券攻排行的 `window_count` 字段
3. 新区间的债券应该显示 `window_count=1`（第一笔）或递增
4. 无记录的债券显示 `window_count=0`

## 六、实施顺序

1. **先执行数据重新填充**（方案A或B）
2. **验证数据正确性**
3. **实施代码修复**（修复1、2、3）
4. **验证功能正确性**
5. **提交**

---

**审核通过后先实施数据重新填充。**
