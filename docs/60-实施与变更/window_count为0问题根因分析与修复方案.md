# window_count为0问题根因分析与修复方案

## 一、根因确认（已验证）

### 问题现象
- 300996 在 09:30:33 的 SQL 查询：`window_count = 7`（正确）
- 前端展示：`window_count = 0`（错误）

### 代码追踪

**1. API入口** `get_stock_ranking()` (行1625)
```python
data = _get_ranking_fast('stock', actual_date, time_str, limit)  # ← 获取排行
data = _enrich_stock_data(data)  # ← 补充债券/行业信息
```

**2. `_get_ranking_fast()` 查询 (行494)**
```sql
SELECT code, name, COUNT(*) as cnt FROM {table}
WHERE time <= :time_str GROUP BY code, name
```
**问题：只查询了 code, name, cnt（总次数），没有 window_count！**

**3. `_enrich_stock_data()` (行358)**
- 补充：bond_code, bond_name, industry_name, is_green_bond
- **没有补充 window_count**

**4. 前端收到的数据结构**
```python
{'code': '300996', 'name': 'XX', 'count': 7, 'rank': 1, 
 'bond_code': '...', 'bond_name': '...', 
 'window_count': 0}  # ← 默认值，因为没有从后端获取
```

## 二、根因结论

**`_get_ranking_fast` 没有从MySQL查询 `window_count` 字段，导致前端展示为默认值0。**

## 三、修复方案（二选一）

### 方案A：修改 `_get_ranking_fast` 查询（推荐）

在SQL中同时获取 `window_count`（取每个code截止时间的最新值）。

**改动点**：`src/gs2026/dashboard2/routes/monitor.py` 行494-550

```python
# 原SQL（路径2）
SELECT code, name, COUNT(*) as cnt FROM {table}
WHERE time <= :time_str GROUP BY code, name

# 新SQL（同时获取window_count）
SELECT 
    t1.code, 
    t1.name, 
    COUNT(*) as cnt,
    t1.window_count  # ← 取最新时间的window_count
FROM {table} t1
INNER JOIN (
    SELECT code, MAX(time) as max_time
    FROM {table}
    WHERE time <= :time_str
    GROUP BY code
) t2 ON t1.code = t2.code AND t1.time = t2.max_time
GROUP BY t1.code, t1.name, t1.window_count
```

**优点**：一次查询，数据准确
**缺点**：SQL稍复杂，但性能可接受

---

### 方案B：新增 `_enrich_window_count` 补充（最小改动）

在 `_enrich_stock_data` 之后，新增函数补充 `window_count`。

**改动点**：`src/gs2026/dashboard2/routes/monitor.py`

```python
def _enrich_window_count(stocks: list, date: str, time_str: str) -> list:
    """补充window_count（从MySQL查询）"""
    if not stocks:
        return stocks
    
    codes = [s['code'] for s in stocks]
    codes_str = "','".join(codes)
    table = f"monitor_gp_top30_{date.replace('-', '')}"
    
    # 取每个code截止时间的最新window_count
    sql = f"""
        SELECT t1.code, t1.window_count
        FROM {table} t1
        INNER JOIN (
            SELECT code, MAX(time) as max_time
            FROM {table}
            WHERE code IN ('{codes_str}') AND time <= '{time_str}'
            GROUP BY code
        ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
    """
    
    engine = _get_shared_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
        wc_map = {r[0]: r[1] for r in rows}
    
    for stock in stocks:
        stock['window_count'] = wc_map.get(stock['code'], 0)
    
    return stocks
```

在 `get_stock_ranking` 中调用：
```python
data = _get_ranking_fast('stock', actual_date, time_str, limit)
data = _enrich_stock_data(data)
data = _enrich_window_count(data, actual_date, time_str)  # ← 新增
```

**优点**：改动小，逻辑清晰
**缺点**：多一次查询（但codes数量有限，性能可接受）

---

## 四、推荐方案

**方案B**（最小改动，逻辑清晰）

理由：
1. `_get_ranking_fast` 是通用函数（stock/bond共用），改它影响面广
2. `_enrich_window_count` 职责单一，只补充缺失字段
3. 与现有 `_enrich_stock_data`、`_enrich_change_pct_and_main_net` 模式一致

## 五、验证方法

修复后，检查300996在09:30:33：
```bash
curl "http://localhost:5000/api/monitor/attack-ranking/stock?date=20250731&time=09:30:33"
# 应返回 window_count: 7（而非0）
```

---

**确认方案B后实施。**
