# 股票上攻排行债券代码不显示问题分析

> 分析时间: 2026-03-31 11:27  
> 问题: 300992的债券代码123160存在但不显示

---

## 一、问题现象

**股票代码**: 300992  
**债券代码**: 123160 (存在但前端不显示)  
**期望**: 显示债券代码和债券名称  
**实际**: 显示 "-"

---

## 二、数据流分析

```
前端请求 /attack-ranking/stock
    ↓
get_stock_ranking() 获取排行数据
    ↓
_process_stock_ranking() 处理数据
    ├── _enrich_stock_data() 补充债券信息 ← 问题可能在这里
    ├── _enrich_change_pct() 添加涨跌幅
    └── 红名单标记
    ↓
返回前端
```

---

## 三、可能原因分析

### 原因1: 缓存未更新

**分析**:
- 股票-债券映射缓存每天更新一次
- 如果300992是新增的可转债标的，缓存可能不包含

**验证方法**:
```python
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
mapping = cache.get_mapping('300992')
print(mapping)
# 如果返回None，说明缓存中没有
```

**解决方案**:
```python
# 强制更新缓存
cache.update_mapping(force=True)
```

---

### 原因2: 债券价格过滤

**分析**:
- 缓存更新时有价格过滤条件
- `min_bond_price=120.0, max_bond_price=250.0`
- 如果123160的价格不在这个范围，会被过滤掉

**验证方法**:
```python
# 检查债券当前价格
from gs2026.monitor.stock_bond_industry_mapping import get_bond_daily_data
bond_data = get_bond_daily_data()
print(bond_data[bond_data['bond_code'] == '123160'])
```

**解决方案**:
调整价格过滤范围或移除价格过滤:
```python
# 修改缓存更新参数
mapping_df = get_stock_bond_industry_mapping(
    min_bond_price=0.0,      # 不设下限
    max_bond_price=1000.0,   # 放宽上限
    redemption_days_threshold=30
)
```

---

### 原因3: 股票代码格式不匹配

**分析**:
- 排行数据中的股票代码可能是 `300992` 或 `300992.SZ`
- 缓存中的股票代码格式需要匹配

**验证方法**:
```python
# 检查排行数据中的代码格式
ranking_data = data_service.get_stock_ranking(limit=100)
for item in ranking_data:
    if '300992' in item.get('code', ''):
        print(f"排行代码: {item['code']}")
        break

# 检查缓存中的代码格式
mapping = cache.get_mapping('300992')
print(f"缓存代码: {mapping.get('stock_code') if mapping else 'None'}")
```

**解决方案**:
统一代码格式处理:
```python
def normalize_stock_code(code):
    """统一股票代码格式"""
    code = str(code).strip()
    # 移除后缀
    if '.' in code:
        code = code.split('.')[0]
    return code

# 在 _enrich_stock_data 中使用
stock_code = normalize_stock_code(stock.get('code', ''))
mapping = cache.get_mapping(stock_code)
```

---

### 原因4: 缓存日期不匹配

**分析**:
- 缓存按日期存储: `stock_bond_mapping:2026-03-31`
- 如果查询时使用的日期不是今天，可能查不到

**验证方法**:
```python
# 检查缓存最新日期
latest_date = cache.get_latest_date()
print(f"缓存最新日期: {latest_date}")

# 检查今天是否有缓存
today = datetime.now().strftime('%Y-%m-%d')
print(f"今天: {today}")
print(f"缓存存在: {cache.redis.exists(f'stock_bond_mapping:{today}')}")
```

**解决方案**:
```python
# 确保使用正确的日期
def get_mapping(self, stock_code: str, date: str = None) -> Optional[Dict]:
    if date is None:
        date = self.get_latest_date()
        # 如果最新日期不是今天，尝试使用今天
        today = datetime.now().strftime('%Y-%m-%d')
        if date != today:
            # 先尝试今天
            mapping_key = self._get_mapping_key(today)
            data = self.redis.hget(mapping_key, str(stock_code))
            if data:
                return json.loads(data)
            # 今天没有，再使用最新日期
            date = self.get_latest_date()
```

---

### 原因5: 数据生成逻辑问题

**分析**:
- `stock_bond_industry_mapping.py` 生成映射时可能过滤掉了某些数据
- 需要检查原始SQL查询

**验证方法**:
```python
from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping
df = get_stock_bond_industry_mapping()
print(df[df['stock_code'] == '300992'])
# 如果为空，说明生成时就被过滤了
```

**可能原因**:
1. 债券价格不在范围内
2. 赎回日期临近
3. 行业数据缺失
4. 债券代码为空

---

## 四、排查步骤

### 步骤1: 验证缓存中是否存在
```python
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()

# 方法1: 直接查询
mapping = cache.get_mapping('300992')
print(f"直接查询结果: {mapping}")

# 方法2: 获取全部映射
all_mapping = cache.get_all_mapping()
print(f"300992在全部映射中: {'300992' in all_mapping}")
if '300992' in all_mapping:
    print(f"映射数据: {all_mapping['300992']}")
```

### 步骤2: 检查原始数据生成
```python
from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping
df = get_stock_bond_industry_mapping(min_bond_price=0, max_bond_price=1000)

# 检查300992
result = df[df['stock_code'] == '300992']
print(f"原始数据: {result}")

# 检查123160
result2 = df[df['bond_code'] == '123160']
print(f"债券数据: {result2}")
```

### 步骤3: 检查前端接收的数据
```javascript
// 浏览器控制台
fetch('/attack-ranking/stock?limit=100')
  .then(r => r.json())
  .then(data => {
    const stock = data.data.find(s => s.code.includes('300992'));
    console.log('300992数据:', stock);
  });
```

---

## 五、解决方案汇总

### 方案A: 强制更新缓存（推荐先尝试）

```python
# 在Python控制台执行
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
result = cache.update_mapping(force=True)
print(result)
```

**适用场景**: 缓存过期或数据变更

### 方案B: 调整价格过滤参数

修改 `stock_bond_mapping_cache.py`:
```python
# 放宽价格限制
mapping_df = get_stock_bond_industry_mapping(
    min_bond_price=0.0,      # 改为0
    max_bond_price=500.0,    # 放宽到500
    redemption_days_threshold=30
)
```

**适用场景**: 债券价格超出默认范围

### 方案C: 统一代码格式

修改 `monitor.py` 中的 `_enrich_stock_data`:
```python
def _normalize_code(code):
    """标准化股票代码"""
    code = str(code).strip()
    if '.' in code:
        code = code.split('.')[0]
    return code

def _enrich_stock_data(stocks: list) -> list:
    # ...
    for stock in stocks:
        stock_code = _normalize_code(stock.get('code', ''))
        mapping = cache.get_mapping(stock_code)
        # ...
```

**适用场景**: 代码格式不匹配

### 方案D: 检查原始数据生成逻辑

检查 `stock_bond_industry_mapping.py` 的SQL查询，确保包含300992。

**适用场景**: 数据生成时就被过滤

---

## 六、快速修复方案

### 立即执行（2分钟）

1. **强制更新缓存**:
```python
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
cache.update_mapping(force=True)
```

2. **刷新前端页面** (Ctrl+F5)

3. **验证是否解决**

### 如果未解决

执行详细排查，确定具体原因后实施对应方案。

---

**文档位置**: `docs/bond_code_missing_analysis.md`

**请先尝试方案A（强制更新缓存），如果无效再执行详细排查。**
