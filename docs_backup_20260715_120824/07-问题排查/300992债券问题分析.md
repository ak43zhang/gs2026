# 300992债券不显示问题 - 完整分析报告

> 分析时间: 2026-03-31 11:56  
> 问题: 股票上攻排行中300992没有显示债券代码123160

---

## 一、问题确认

### 1.1 缓存数据检查

```
缓存元数据:
  创建时间: 2026-03-31 00:25:10  ← 凌晨生成！
  总记录数: 5496
  价格范围: [120.0, 250.0]  ← 旧的价格范围

300992缓存数据:
  stock_code: '300992'
  bond_code: ''  ← 空字符串！
  bond_name: ''
```

### 1.2 问题根源

**根本原因**: 缓存是凌晨生成的，当时：
1. `stock_bond_industry_mapping.py` 还未修复（使用全局最新日期）
2. 价格范围是 `[120.0, 250.0]`

所以300992在缓存生成时没有关联到债券123160。

---

## 二、调用链路分析

```
前端请求 /attack-ranking/stock
    ↓
get_stock_ranking() [monitor.py]
    ↓
data_service.get_stock_ranking() / get_ranking_at_time()
    ↓
_process_stock_ranking() [monitor.py]
    ├── _enrich_stock_data() ← 问题在这里！
    │       ↓
    │   cache.get_mapping('300992')
    │       ↓
    │   Redis: stock_bond_mapping:2026-03-31
    │       ↓
    │   返回: {'bond_code': '', ...} ← 空字符串！
    │
    ├── _enrich_change_pct()
    └── 红名单标记
    ↓
返回前端
```

---

## 三、解决方案

### 方案A: 强制更新缓存（推荐）

```python
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()

# 强制更新缓存（使用修复后的代码）
result = cache.update_mapping(
    min_bond_price=0.0,      # 放宽价格限制
    max_bond_price=500.0,
    force=True               # 强制更新，即使已存在
)

print(result)
```

**预期结果**:
- 缓存重新生成
- 300992将关联到债券123160
- 前端刷新后显示正常

---

### 方案B: 删除缓存重新生成

```python
from gs2026.utils import redis_util
redis_client = redis_util._get_redis_client()

# 删除今天的缓存
redis_client.delete('stock_bond_mapping:2026-03-31')
redis_client.delete('stock_bond_mapping:latest_date')
redis_client.delete('stock_bond_mapping:meta')

# 重新生成缓存
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
cache.update_mapping(min_bond_price=0.0, max_bond_price=500.0)
```

---

### 方案C: 修改缓存读取逻辑（兜底方案）

如果缓存中bond_code为空，尝试实时查询：

```python
# 修改 _enrich_stock_data 函数
def _enrich_stock_data(stocks: list) -> list:
    cache = get_cache()
    
    for stock in stocks:
        stock_code = stock.get('code', '')
        mapping = cache.get_mapping(stock_code)
        
        if mapping and mapping.get('bond_code'):
            # 缓存中有债券信息
            stock['bond_code'] = mapping['bond_code']
            stock['bond_name'] = mapping['bond_name']
        else:
            # 缓存中无债券信息，尝试实时查询
            from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping
            import pandas as pd
            
            try:
                df = get_stock_bond_industry_mapping(min_bond_price=0, max_bond_price=1000)
                row = df[df['stock_code'] == stock_code]
                if not row.empty and pd.notna(row.iloc[0]['bond_code']):
                    stock['bond_code'] = row.iloc[0]['bond_code']
                    stock['bond_name'] = row.iloc[0]['bond_name']
                else:
                    stock['bond_code'] = '-'
                    stock['bond_name'] = '-'
            except Exception:
                stock['bond_code'] = '-'
                stock['bond_name'] = '-'
        
        stock['industry_name'] = mapping.get('industry_name', '-') if mapping else '-'
    
    return stocks
```

---

## 四、推荐实施步骤

### 立即执行（2分钟）

1. **强制更新缓存**:
```python
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
cache.update_mapping(min_bond_price=0.0, max_bond_price=500.0, force=True)
```

2. **验证缓存**:
```python
mapping = cache.get_mapping('300992')
print(mapping)
# 预期: {'bond_code': '123160', 'bond_name': '泰福转债', ...}
```

3. **刷新前端页面** (Ctrl+F5)

---

## 五、长期优化建议

### 1. 缓存自动更新机制

添加定时任务，每天开盘前自动更新缓存：
```python
# 在 app.py 中添加启动时检查
@app.before_first_request
def init_stock_bond_cache():
    cache = get_cache()
    today = datetime.now().strftime('%Y-%m-%d')
    mapping_key = f'stock_bond_mapping:{today}'
    
    if not cache.redis.exists(mapping_key):
        # 今天缓存不存在，重新生成
        cache.update_mapping(min_bond_price=0.0, max_bond_price=500.0)
```

### 2. 缓存版本控制

在元数据中添加代码版本，当代码更新时自动刷新缓存：
```python
meta = {
    "version": "1.1",  # 代码版本
    "code_hash": hash_of_mapping_py,  # 代码文件hash
    # ...
}
```

### 3. 缓存预热

在每天开盘前预热缓存：
```python
# 定时任务：每天 09:00 更新缓存
def scheduled_cache_update():
    cache = get_cache()
    cache.update_mapping(min_bond_price=0.0, max_bond_price=500.0, force=True)
```

---

**文档位置**: `docs/300992_bond_issue_analysis.md`

**根本原因**: 缓存是凌晨生成的（使用旧代码），需要强制更新缓存。

**推荐方案**: 方案A（强制更新缓存）
