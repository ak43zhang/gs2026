# 区间次数跨区间显示错误问题分析与修复方案

## 一、问题现象

- 09:40:36 已经是新区间（09:40-09:49）
- 但显示的还是旧区间（09:30-09:39）的累计次数
- 期望：新区间次数应该从1开始（或0）

## 二、根因分析

### 当前实现逻辑

**1. 写入时（monitor_stock.py）**
```python
window_count = get_window_count(code, date_str, time_full, table_name, engine)
# 写入MySQL的window_count字段是该tick所在区间的累计次数
```

例如：
- 09:39:58 写入，`window_count=5`（09:30-09:39区间累计5次）
- 09:40:15 写入，`window_count=1`（09:40-09:49区间第1次）

**2. 查询时（_get_stock_window_count_batch）**
```sql
SELECT t1.code, t1.window_count
FROM {table_name} t1
INNER JOIN (
    SELECT code, MAX(time) as max_time  -- 取截止时间前的最新记录
    WHERE time <= '{time_str}'
    GROUP BY code
) t2 ON t1.code=t2.code AND t1.time=t2.max_time
```

**问题：查询取的是"最新记录的window_count值"，不是"当前时间所在区间的次数"**

例如查询 09:40:36：
- 最新记录可能是 09:39:58 的，`window_count=5`（旧区间）
- 但 09:40:36 属于新区间，应该查 09:40:00-09:40:36 的累计次数

## 三、解决方案

### 方案A：前端实时计算当前区间次数（推荐）

修改 `_get_stock_window_count_batch`，根据查询时间计算当前区间，实时统计。

**SQL改造**：
```python
def _get_stock_window_count_batch(date: str, time_str: str, stock_codes: list) -> dict:
    """
    根据查询时间实时计算当前区间次数（而非取MySQL存储的历史值）
    """
    if not stock_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import text
        
        table_name = f"monitor_gp_top30_{date}"
        codes_str = "','".join(stock_codes)
        
        # 计算当前时间所在10分钟区间的起始
        # 例如 09:40:36 -> 09:40:00
        hh = time_str[:2]
        mm = int(time_str[3:5])
        window_start = f"{hh}:{(mm//10)*10:02d}:00"
        
        # 查询当前区间内各code的出现次数（实时计算）
        sql = f"""
            SELECT code, COUNT(*) as window_count
            FROM {table_name}
            WHERE code IN ('{codes_str}') 
              AND time >= '{window_start}' 
              AND time <= '{time_str}'
            GROUP BY code
        """
        
        engine = _get_shared_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return {row[0]: row[1] for row in result}
            
    except Exception as e:
        print(f"计算股票window_count失败: {e}")
        return {}
```

**优点**：
- 真正反映"当前区间次数"
- 与monitor写入逻辑解耦
- 债券同样适用（可统一修改）

**缺点**：
- 每次查询都要COUNT，性能稍差（但code数量有限，可接受）

---

### 方案B：MySQL增加区间标识字段

增加 `window_start` 字段，存储该记录所属区间的起始时间。

**修改点**：
1. `monitor_stock.py` 写入时计算 `window_start` 并存储
2. 查询时根据当前时间计算 `window_start`，匹配该区间所有记录COUNT

**优点**：查询可用索引，性能更好
**缺点**：需要改表结构，迁移历史数据

---

## 四、推荐方案

**方案A（前端实时计算）**

理由：
1. 改动最小，不改表结构
2. 逻辑清晰：查询时根据当前时间动态计算区间
3. 债券和股票可统一处理

## 五、验证方法

修复后：
1. 09:39:58 某股票 window_count=5（09:30-09:39区间5次）
2. 09:40:15 该股票 window_count=1（新区间第1次）
3. 查询 09:40:36 应返回 1（或2，取决于中间是否有其他tick）

---

**确认方案A后实施。**
