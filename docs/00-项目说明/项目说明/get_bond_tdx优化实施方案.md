# get_bond_tdx 优化实施方案

## 当前现状

### 现有 `get_bond_tdx()` 实现问题

```python
def get_bond_tdx():
    # 问题1：每次调用都新建连接
    api = TdxHq_API()
    for host, port in tdx_servers:
        api.connect(host, port, time_out=3)  # 每次连接
    
    # 问题2：每次调用都获取全市场代码列表（480只）
    bonds = []
    count = api.get_security_count(0)  # 深圳
    for start in range(0, count, 1000):
        items = api.get_security_list(0, start)  # 遍历所有股票
    
    # 问题3：没有过滤，获取所有转债
    all_quotes = []
    for i in range(0, len(bonds), 80):
        quotes = api.get_security_quotes(params)  # 获取全部
    
    # 问题4：价格精度问题（未除以100）
    price = q.get('price', 0)  # 原始值需要除以100
    
    finally:
        api.disconnect()  # 每次断开
```

**问题总结**：
1. 每次调用都新建连接/断开（约50-100ms开销）
2. 每次调用都获取全市场代码列表（约100-200ms开销）
3. 没有过滤机制，获取全部480只转债
4. 价格精度错误（TDX返回价格需除以100）

---

## 优化方案

### 方案核心：连接复用 + 代码缓存 + 有效数据过滤

#### 1. 连接复用（连接池模式）

```python
# 模块级连接缓存
_tdx_api = None
_tdx_connected = False
_tdx_last_used = 0

def get_tdx_api():
    """获取或创建TdxHq_API连接（带复用）"""
    global _tdx_api, _tdx_connected, _tdx_last_used
    
    # 检查现有连接是否有效
    if _tdx_api and _tdx_connected:
        # 可选：检查连接是否仍然活跃
        return _tdx_api
    
    # 创建新连接
    api = TdxHq_API()
    for host, port in tdx_servers:
        try:
            api.connect(host, port, time_out=3)
            _tdx_api = api
            _tdx_connected = True
            _tdx_last_used = time.time()
            return api
        except:
            continue
    
    return None
```

#### 2. 代码缓存（避免每次获取全市场列表）

```python
# 模块级代码缓存
_bond_codes_cache = None
_bond_codes_cache_time = 0
_CACHE_TTL = 3600  # 1小时缓存

def get_bond_codes_cached(api):
    """获取可转债代码列表（带缓存）"""
    global _bond_codes_cache, _bond_codes_cache_time
    
    now = time.time()
    if _bond_codes_cache and (now - _bond_codes_cache_time) < _CACHE_TTL:
        return _bond_codes_cache
    
    # 重新获取
    bonds = []
    # ... 获取深圳12xxxx和上海11xxxx ...
    
    _bond_codes_cache = bonds
    _bond_codes_cache_time = now
    return bonds
```

#### 3. 只采集有效数据（价格>0且成交量>0）

```python
def get_bond_tdx(filter_valid=True):
    """
    通过pytdx获取可转债实时行情
    
    Args:
        filter_valid: 是否只返回有效数据（价格>0且成交量>0）
    """
    api = get_tdx_api()
    if not api:
        return pd.DataFrame()
    
    bonds = get_bond_codes_cached(api)
    
    # 批量获取行情
    all_quotes = []
    for i in range(0, len(bonds), 80):
        batch = bonds[i:i+80]
        params = [(m, c) for m, c, n in batch]
        quotes = api.get_security_quotes(params)
        if quotes:
            all_quotes.extend(quotes)
    
    # 转换为统一结构（价格除以100）
    rows = []
    valid_count = 0
    invalid_count = 0
    
    for q in all_quotes:
        code = q.get('code', '')
        # 价格精度修正：除以100
        price = q.get('price', 0) / 100
        pre_close = q.get('last_close', 0) / 100
        open_price = q.get('open', 0) / 100
        high = q.get('high', 0) / 100
        low = q.get('low', 0) / 100
        volume = q.get('vol', 0)
        amount = q.get('amount', 0)
        
        # 【新增】过滤无效数据
        if filter_valid and (price <= 0 or volume <= 0):
            invalid_count += 1
            continue  # 跳过无效数据
        
        valid_count += 1
        
        change_pct = 0
        if pre_close and pre_close > 0:
            change_pct = (price - pre_close) / pre_close * 100
        
        rows.append({
            'bond_code': code,
            'bond_name': name_map.get(code, ''),
            'price': price,
            'open': open_price,
            'high': high,
            'low': low,
            'pre_close': pre_close,
            'volume': volume,
            'amount': amount,
            'change_pct': round(change_pct, 4),
        })
    
    df = pd.DataFrame(rows)
    
    if filter_valid:
        logger.info(f"[tdx] 获取{len(df)}只有效转债（过滤{invalid_count}只无效）")
    else:
        logger.info(f"[tdx] 获取{len(df)}只转债")
    
    return df
```

---

## 优化效果预期

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 单次调用耗时 | 500-800ms | 200-400ms | 50%↓ |
| 连接开销 | 每次50-100ms | 复用0ms | 100%↓ |
| 代码获取开销 | 每次100-200ms | 缓存0ms | 100%↓ |
| 有效数据比例 | 100%（含无效） | ~95%有效 | 质量↑ |
| 价格精度 | 错误（未除100） | 正确（除100） | 精度↑ |

---

## 实施步骤

1. **添加模块级缓存变量**（连接、代码列表）
2. **创建 `get_tdx_api()` 连接复用函数**
3. **创建 `get_bond_codes_cached()` 代码缓存函数**
4. **修改 `get_bond_tdx()` 实现新逻辑**
5. **添加价格精度修正（除以100）**
6. **添加有效数据过滤（可选参数）**

---

## 关键代码变更

### 新增模块级变量
```python
# TDX连接缓存
_tdx_api = None
_tdx_connected = False
_tdx_last_used = 0

# 债券代码缓存
_bond_codes_cache = None
_bond_codes_cache_time = 0
_CACHE_TTL = 3600
```

### 修改get_bond_tdx函数签名
```python
def get_bond_tdx(filter_valid=True):  # 新增filter_valid参数
    ...
```

### 价格精度修正
```python
# 所有价格类字段除以100
price = q.get('price', 0) / 100
pre_close = q.get('last_close', 0) / 100
open_price = q.get('open', 0) / 100
high = q.get('high', 0) / 100
low = q.get('low', 0) / 100
```

---

**审核状态**: 待审核
