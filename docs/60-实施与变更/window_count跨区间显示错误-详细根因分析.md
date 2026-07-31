# window_count 跨区间显示错误 - 详细根因分析与修复方案

## 一、实际数据验证

### 问题场景确认

**股票 300663 的时间线：**
| 时间 | window_count | 所属区间 | 说明 |
|------|-------------|---------|------|
| 09:37:54 | 17 | 09:30:00 | 旧区间累计17次 |
| 09:40:03 | **无记录** | - | 新区间尚未出现 |

**前端查询 09:40:03 时的SQL行为：**
```sql
SELECT t1.code, t1.window_count  -- 返回17（旧区间值）
FROM monitor_gp_top30_20260731 t1
INNER JOIN (
    SELECT code, MAX(time) as max_time  -- 找到09:37:54（旧区间）
    WHERE code='300663' AND time <= '09:40:03'
) t2 ON t1.time=t2.max_time
```

**问题**：该股票在09:40:00-09:40:03**新区间尚未出现**，但SQL返回的是**09:37:54旧区间的记录**（window_count=17）。

### 用户期望
- 09:40:03 查询应返回 **0**（新区间尚未出现）
- 或等该股票在09:40:XX出现后，返回 **1**（新区间第1次）
- **绝不返回17**（旧区间值）

---

## 二、根因确认

**前端SQL逻辑错误**：
- 当前：取"该股票在time_str前的最新记录的window_count值"
- 正确：应该取"当前区间内的出现次数"

**关键区别**：
- 旧逻辑：不管记录属于哪个区间，只取最新记录的window_count
- 新逻辑：只统计当前区间（如09:40:00-09:40:03）内的记录数

---

## 三、修复方案

### 方案A：实时计算当前区间次数（推荐）

**修改 `_get_stock_window_count_batch`**：

```python
def _get_stock_window_count_batch(date: str, time_str: str, stock_codes: list) -> dict:
    """
    根据查询时间实时计算当前区间次数
    而非取MySQL存储的历史记录值
    """
    if not stock_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import text
        
        table_name = f"monitor_gp_top30_{date}"
        codes_str = "','".join(stock_codes)
        
        # 【关键】计算当前10分钟区间的起始
        # 09:40:03 -> 09:40:00
        hh = time_str[:2]
        mm = int(time_str[3:5])
        window_start = f"{hh}:{(mm//10)*10:02d}:00"
        
        # 【关键】查询当前区间内各code的出现次数（实时计算）
        # 不是取最新记录的window_count，而是COUNT当前区间的记录数
        sql = f"""
            SELECT code, COUNT(*) as window_count
            FROM {table_name}
            WHERE code IN ('{codes_str}') 
              AND time >= '{window_start}'   -- 当前区间起始
              AND time <= '{time_str}'        -- 查询时间
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

**效果**：
- 300663 在 09:40:03 查询：返回 **0**（该区间尚无记录）
- 300663 在 09:41:00 查询（假设09:40:45出现过）：返回 **1**

---

### 方案B：前端过滤（备选）

保持SQL不变，但在Python中过滤掉不属于当前区间的记录：

```python
def _get_stock_window_count_batch(date: str, time_str: str, stock_codes: list) -> dict:
    # ... 原SQL查询 ...
    
    # 计算当前区间起始
    hh = time_str[:2]
    mm = int(time_str[3:5])
    window_start = f"{hh}:{(mm//10)*10:02d}:00"
    
    # 过滤：只保留属于当前区间的记录
    result = {}
    for row in conn.execute(text(sql)).fetchall():
        code = row[0]
        record_time = row[1]  # 需要SQL返回time字段
        record_window = f"{record_time[:2]}:{(int(record_time[3:5])//10)*10:02d}:00"
        
        if record_window == window_start:  # 属于当前区间
            result[code] = row[2]
        else:
            result[code] = 0  # 不属于当前区间，返回0
    
    return result
```

**缺点**：需要SQL返回time字段，且逻辑复杂。

---

## 四、推荐方案

**方案A（实时计算）**

理由：
1. 逻辑清晰：直接COUNT当前区间，不依赖window_count字段
2. 数据准确：真正反映"当前区间内的出现次数"
3. 与monitor写入逻辑解耦：不依赖写入时的window_count计算

---

## 五、债券同步修改

债券的 `_get_bond_window_count_batch` 同样需要修改，逻辑完全一致。

---

## 六、验证方法

修复后验证 300663：
1. 09:40:02 查询 → 返回 **0**（新区间尚无记录）
2. 等 09:40:XX 该股票出现后 → 返回 **1**
3. 09:41:00 查询 → 返回 **1**（假设只出现1次）

---

**确认方案A后实施。**
