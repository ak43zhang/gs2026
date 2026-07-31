# 债券 vs 股票 window_count 差异性分析与最终方案

## 一、核心差异对比

| 维度 | 债券上攻排行 | 股票上攻排行 |
|------|-------------|-------------|
| **API入口** | `get_bond_ranking()` (行1907) | `get_stock_ranking()` (行1625) |
| **获取排行** | `_get_ranking_fast('bond', ...)` | `_get_ranking_fast('stock', ...)` |
| **数据补充** | `_enrich_bond_data()` (行1010) | `_enrich_stock_data()` (行358) |
| **window_count查询** | ✅ **有** `_get_bond_window_count_batch()` (行966) | ❌ **无** |
| **window_count填充** | ✅ **有** (行1132) | ❌ **无** |

## 二、债券实现逻辑（正确）

```python
# _enrich_bond_data 中明确查询并填充 window_count

# 【新增】查询window_count（取截止时间的最新值）
window_count_map = _get_bond_window_count_batch(date, query_time, bond_codes)  # 行1095

# 填充数据
for bond in bonds:
    code = bond.get('code', '')
    # ... 其他字段 ...
    bond['window_count'] = window_count_map.get(code, 0)  # 行1132
```

`_get_bond_window_count_batch` SQL (行989-992)：
```sql
SELECT t1.code, t1.window_count
FROM {table_name} t1
INNER JOIN (
    SELECT code, MAX(time) as max_time
    FROM {table_name}
    WHERE code IN ('{codes_str}') AND time <= '{time_str}'
    GROUP BY code
) t2 ON t1.code = t2.code AND t1.time = t2.max_time
```

## 三、股票实现逻辑（缺失）

```python
# _enrich_stock_data 中**没有** window_count 查询和填充

# 现有逻辑只补充：
- bond_code
- bond_name  
- industry_name
- is_green_bond

# window_count 完全缺失！
```

## 四、根因确认

**股票 window_count 为 0 的根本原因：**

1. `_get_ranking_fast` 只返回 `code, name, count`（总次数），**不返回 `window_count`**
2. `_enrich_stock_data` **没有** 像债券那样查询和填充 `window_count`
3. 前端展示时，`window_count` 字段不存在或为默认值 **0**

## 五、最终解决方案

**直接借鉴债券方案**：在 `_enrich_stock_data` 之后，新增 `_enrich_stock_window_count` 函数，逻辑完全复制 `_get_bond_window_count_batch`。

### 具体改动

**文件**: `src/gs2026/dashboard2/routes/monitor.py`

**① 新增函数**（放在 `_get_bond_window_count_batch` 附近）：

```python
def _get_stock_window_count_batch(date: str, time_str: str, stock_codes: list) -> dict:
    """
    批量获取股票的window_count（取截止时间的最新值）
    直接借鉴债券的 _get_bond_window_count_batch 实现
    """
    if not stock_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import text
        
        table_name = f"monitor_gp_top30_{date}"
        codes_str = "','".join(stock_codes)
        
        # 取每个股票截止时间的最新window_count（完全复制债券逻辑）
        sql = f"""
            SELECT t1.code, t1.window_count
            FROM {table_name} t1
            INNER JOIN (
                SELECT code, MAX(time) as max_time
                FROM {table_name}
                WHERE code IN ('{codes_str}') AND time <= '{time_str}'
                GROUP BY code
            ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
        """
        
        engine = _get_shared_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return {row[0]: row[1] for row in result}
            
    except Exception as e:
        print(f"批量获取股票window_count失败: {e}")
        return {}
```

**② 修改 `_enrich_stock_data`** 或 **在调用处补充**：

方案A（修改函数，推荐）：
```python
def _enrich_stock_data(stocks: list, date: str = None, time_str: str = None) -> list:
    """
    为股票数据添加债券、行业信息，以及绿名单标记和window_count
    """
    if not stocks:
        return stocks
    
    try:
        # ... 现有逻辑：获取映射缓存、绿名单等 ...
        
        # 【新增】借鉴债券：查询window_count
        if date and time_str:
            stock_codes = [s.get('code', '') for s in stocks if s.get('code')]
            window_count_map = _get_stock_window_count_batch(date, time_str, stock_codes)
            for stock in stocks:
                stock['window_count'] = window_count_map.get(stock.get('code'), 0)
        else:
            for stock in stocks:
                stock['window_count'] = 0
        
        return stocks
        
    except Exception as e:
        print(f"[enrich_stock_data失败] {e}")
        # 失败时默认0
        for stock in stocks:
            stock['window_count'] = 0
        return stocks
```

方案B（在调用处补充，最小侵入）：
```python
# 在 get_stock_ranking 的3处时间轴模式后调用
data = _get_ranking_fast('stock', actual_date, time_str, limit)
data = _enrich_stock_data(data)
data = _enrich_stock_window_count(data, actual_date, time_str)  # 新增函数
```

## 六、验证方法

修复后验证300996在09:30:33：
```bash
curl "http://localhost:5000/api/monitor/attack-ranking/stock?date=20250731&time=09:30:33" | grep -A5 "300996"
```

应返回：
```json
{
  "code": "300996",
  "name": "...",
  "count": 7,
  "window_count": 7,  // ← 应为7，不是0
  ...
}
```

## 七、结论

**直接借鉴债券的 `_get_bond_window_count_batch` 实现，为股票新增相同的查询逻辑。**

这是最小改动、最可靠的方案，债券已验证正确运行。

---

**确认后实施。**
