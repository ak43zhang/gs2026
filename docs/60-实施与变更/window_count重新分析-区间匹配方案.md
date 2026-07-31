# 重新分析：用户期望 vs 实际差异

## 一、用户的核心质疑

用户说：
> "window_count本身不就是计算区间次数的吗？"
> "如果通过时间查询不到直接设置0不可以吗？"
> "有值的直接使用"

**我理解的用户期望**：
- 查询时间点（如09:40:03）
- 确定该时间所在的**当前区间**（09:40:00-09:49:59）
- 对于每个股票：
  - 如果该股票在**当前区间**内有记录 → 使用该记录的window_count（区间累计次数）
  - 如果该股票在**当前区间**内无记录 → 显示0

## 二、实际行为分析

### 当前前端SQL逻辑
```sql
-- 取该股票在time_str前的最新记录（不管哪个区间）
SELECT t1.window_count
WHERE time <= '09:40:03'
ORDER BY time DESC
```

**问题**：返回的是**09:37:54旧区间的记录**（window_count=17），而不是**09:40:00新区间的记录**。

### 实际数据验证

**股票 300663**：
- 09:37:54 旧区间记录：window_count=17
- 09:40:03 查询时：该股票在新区间**尚无记录**

**当前行为**：返回17（错误）
**期望行为**：返回0（正确，新区间还没出现过）

**股票 001258**：
- 09:40:00 新区间记录：window_count=1
- 09:40:03 查询时：该股票在新区间**有记录**

**当前行为**：返回1（正确）
**期望行为**：返回1（正确）

## 三、关键差异

| 场景 | 当前SQL行为 | 用户期望 |
|------|-----------|---------|
| 股票在新区间**无记录** | 返回旧区间最新值（17） | 返回0 |
| 股票在新区间**有记录** | 返回新区间值（1） | 返回新区间值（1） |

**问题只在第一种情况**：当股票跨区间后尚未出现时，不应该显示旧区间的值。

## 四、用户期望的方案理解

用户说"有值的直接使用"，意思是：
- 如果能在**当前区间**找到记录，直接用那个记录的window_count
- 如果找不到，显示0

**这不是实时计算COUNT，而是区间匹配查询**。

## 五、正确方案（区间匹配）

### 方案B：区间匹配查询（符合用户期望）

```python
def _get_stock_window_count_batch(date: str, time_str: str, stock_codes: list) -> dict:
    """
    查询当前区间内的window_count
    如果当前区间无记录，返回0（而非取旧区间值）
    """
    if not stock_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import text
        
        table_name = f"monitor_gp_top30_{date}"
        codes_str = "','".join(stock_codes)
        
        # 【关键】计算当前10分钟区间的起始和结束
        hh = time_str[:2]
        mm = int(time_str[3:5])
        window_start = f"{hh}:{(mm//10)*10:02d}:00"
        window_end = f"{hh}:{(mm//10)*10+9:02d}:59"
        
        # 【关键】只查询当前区间内的记录
        sql = f"""
            SELECT t1.code, t1.window_count
            FROM {table_name} t1
            INNER JOIN (
                SELECT code, MAX(time) as max_time
                FROM {table_name}
                WHERE code IN ('{codes_str}') 
                  AND time >= '{window_start}'   -- 当前区间起始
                  AND time <= '{time_str}'        -- 查询时间
                GROUP BY code
            ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
        """
        
        engine = _get_shared_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            # 只返回当前区间有记录的股票
            current_window_counts = {row[0]: row[1] for row in result}
            
            # 【关键】对于当前区间无记录的股票，返回0
            all_counts = {}
            for code in stock_codes:
                all_counts[code] = current_window_counts.get(code, 0)
            
            return all_counts
            
    except Exception as e:
        print(f"查询股票window_count失败: {e}")
        return {}
```

**与当前SQL的区别**：
- 当前：只限制 `time <= time_str`（可能取到旧区间记录）
- 新方案：增加 `time >= window_start`（只取当前区间记录）

**效果**：
- 300663 在 09:40:03：当前区间（09:40:00-09:40:03）无记录 → 返回0 ✓
- 001258 在 09:40:03：当前区间有记录（09:40:00）→ 返回1 ✓

## 六、方案对比

| 方案 | 逻辑 | 优点 | 缺点 |
|------|------|------|------|
| A（实时COUNT） | COUNT当前区间记录数 | 完全准确 | 性能稍差（每次COUNT） |
| B（区间匹配） | 取当前区间最新记录的window_count | 性能好，符合用户"有值直接用" | 依赖写入的window_count正确 |

**用户期望的是方案B**：
- "window_count本身就是计算区间次数的" → 直接用写入的window_count
- "有值的直接使用" → 取当前区间的记录
- "查不到设置0" → 当前区间无记录则0

## 七、结论

**推荐方案B（区间匹配查询）**

理由：
1. 完全符合用户描述的期望
2. 性能更好（不用实时COUNT）
3. 复用已有的window_count字段（该字段就是区间次数）

**核心改动**：SQL增加 `time >= window_start` 条件，确保只查询当前区间的记录。

---

**确认方案B后实施。**
