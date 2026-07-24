# get_bond_tdx 函数修改方案 v1.0

## 一、当前问题

当前 `get_bond_tdx()` 实现：
1. 先获取可转债代码列表（`get_security_list`）
2. 再批量获取行情（`get_security_quotes`）

**问题**：`get_security_quotes` 返回的是**最新快照**，不是分钟K线。你之前说的"1分钟一个价格"可能是误解，或者你看到的是其他地方的缓存/处理逻辑。

**实际**：`get_security_quotes` 本身就是**实时快照**，每次调用返回当前最新价格，可以做到3秒更新。

---

## 二、确认当前行为

先验证当前 `get_bond_tdx` 是否真的返回1分钟级数据：

```python
# 测试脚本：连续调用10次，看价格是否变化
from gs2026.monitor.monitor_bond import get_bond_tdx
import time

code = '123257'  # 选一只活跃的债

for i in range(10):
    df = get_bond_tdx()
    if not df.empty and code in df['bond_code'].values:
        row = df[df['bond_code'] == code].iloc[0]
        print(f"{i+1}: {time.strftime('%H:%M:%S')} - {code} price={row['price']}, change_pct={row['change_pct']}")
    else:
        print(f"{i+1}: {time.strftime('%H:%M:%S')} - {code} not found")
    time.sleep(3)  # 等3秒再试
```

**如果价格每3秒变化** → 当前实现已经满足需求，无需修改。

**如果价格1分钟才变一次** → 可能是：
- 数据本身的问题（交易所只推送分钟级）
- 或者 `get_security_quotes` 有缓存

---

## 三、如果确实需要修改

### 3.1 可能的原因

| 原因 | 说明 | 解决 |
|------|------|------|
| TDX服务器缓存 | 某些服务器可能缓存行情 | 换服务器或直连L2 |
| 连接复用问题 | 长连接下数据不刷新 | 每次短连接 |
| 数据字段问题 | 用了 `close` 而不是 `price` | 检查字段 |

### 3.2 修改方案

#### 方案A：强制短连接（每次新建连接）

```python
def get_bond_tdx():
    """通过pytdx获取可转债实时行情"""
    try:
        from pytdx.hq import TdxHq_API

        tdx_servers = [
            ('202.108.253.139', 80),
            ('123.125.108.90', 7709)
        ]

        api = TdxHq_API()
        connected = False
        for host, port in tdx_servers:
            try:
                api.connect(host, port, time_out=3)
                connected = True
                break
            except:
                continue

        if not connected:
            logger.warning("[tdx] 所有HQ服务器连接失败")
            return pd.DataFrame()

        try:
            # 获取可转债代码列表（缓存起来，不用每次都取）
            bonds = _get_cached_bond_list()
            if not bonds:
                bonds = _fetch_and_cache_bond_list(api)

            # 批量获取最新行情（每次80只）
            all_quotes = []
            for i in range(0, len(bonds), 80):
                batch = bonds[i:i+80]
                params = [(m, c) for m, c, n in batch]
                quotes = api.get_security_quotes(params)
                if quotes:
                    all_quotes.extend(quotes)

            # 转换为统一结构
            rows = []
            name_map = {c: n for m, c, n in bonds}
            
            for q in all_quotes:
                code = q.get('code', '')
                # 关键：用实时价格字段
                price = q.get('price', 0)  # 当前最新价
                
                # 如果 price 为0，尝试其他字段
                if price == 0:
                    price = q.get('last_price', 0)  # 有些服务器用这个
                
                pre_close = q.get('last_close', 0)
                
                rows.append({
                    'bond_code': code,
                    'bond_name': name_map.get(code, ''),
                    'price': price,
                    'open': q.get('open', 0),
                    'high': q.get('high', 0),
                    'low': q.get('low', 0),
                    'pre_close': pre_close,
                    'volume': q.get('vol', 0),
                    'amount': q.get('amount', 0),
                    'change_pct': _calc_change_pct(price, pre_close),
                })

            df = pd.DataFrame(rows)
            logger.info(f"[tdx] 获取{len(df)}只转债实时行情")
            return df

        finally:
            api.disconnect()  # 确保断开，下次新建连接

    except Exception as e:
        logger.error(f"[tdx] 获取行情失败: {e}")
        return pd.DataFrame()


# 缓存可转债列表，避免每次都获取
def _get_cached_bond_list():
    """从缓存获取可转债列表"""
    # 可以用全局变量或文件缓存
    if hasattr(_get_cached_bond_list, '_cache'):
        return _get_cached_bond_list._cache
    return None

def _fetch_and_cache_bond_list(api):
    """获取并缓存可转债列表"""
    bonds = []
    # 深圳 (market=0): 12开头
    count = api.get_security_count(0)
    for start in range(0, count, 1000):
        items = api.get_security_list(0, start)
        if items:
            for s in items:
                if s['code'].startswith('12'):
                    bonds.append((0, s['code'], s.get('name', '')))
    # 上海 (market=1): 11开头
    count = api.get_security_count(1)
    for start in range(0, count, 1000):
        items = api.get_security_list(1, start)
        if items:
            for s in items:
                if s['code'].startswith('11'):
                    bonds.append((1, s['code'], s.get('name', '')))
    
    _get_cached_bond_list._cache = bonds
    return bonds


def _calc_change_pct(price, pre_close):
    if pre_close and pre_close > 0:
        return round((price - pre_close) / pre_close * 100, 4)
    return 0
```

#### 方案B：连接池复用（推荐，性能更好）

```python
class TdxConnectionPool:
    """pytdx连接池，复用TCP连接但强制刷新数据"""
    
    _instance = None
    _api = None
    _last_used = 0
    
    @classmethod
    def get_api(cls):
        if cls._api is None:
            cls._api = TdxHq_API()
            cls._connect()
        return cls._api
    
    @classmethod
    def _connect(cls):
        servers = [
            ('202.108.253.139', 80),
            ('123.125.108.90', 7709)
        ]
        for host, port in servers:
            try:
                cls._api.connect(host, port, time_out=3)
                cls._last_used = time.time()
                return True
            except:
                continue
        return False
    
    @classmethod
    def close(cls):
        if cls._api:
            cls._api.disconnect()
            cls._api = None


def get_bond_tdx():
    """通过pytdx获取可转债实时行情"""
    try:
        from pytdx.hq import TdxHq_API
        
        api = TdxConnectionPool.get_api()
        if api is None:
            return pd.DataFrame()
        
        # 获取可转债列表（缓存）
        bonds = _get_cached_bond_list()
        if not bonds:
            # 首次获取
            bonds = []
            for market in [0, 1]:
                count = api.get_security_count(market)
                for start in range(0, count, 1000):
                    items = api.get_security_list(market, start)
                    if items:
                        for s in items:
                            code = s['code']
                            if code.startswith('12') or code.startswith('11'):
                                bonds.append((market, code, s.get('name', '')))
            _get_cached_bond_list._cache = bonds
        
        # 批量获取最新行情
        all_quotes = []
        for i in range(0, len(bonds), 80):
            batch = bonds[i:i+80]
            params = [(m, c) for m, c, n in batch]
            quotes = api.get_security_quotes(params)
            if quotes:
                all_quotes.extend(quotes)
        
        # 转换为统一结构
        rows = []
        name_map = {c: n for m, c, n in bonds}
        
        for q in all_quotes:
            code = q.get('code', '')
            price = q.get('price', 0)
            pre_close = q.get('last_close', 0)
            
            rows.append({
                'bond_code': code,
                'bond_name': name_map.get(code, ''),
                'price': price,
                'open': q.get('open', 0),
                'high': q.get('high', 0),
                'low': q.get('low', 0),
                'pre_close': pre_close,
                'volume': q.get('vol', 0),
                'amount': q.get('amount', 0),
                'change_pct': _calc_change_pct(price, pre_close),
            })
        
        df = pd.DataFrame(rows)
        logger.info(f"[tdx] 获取{len(df)}只转债实时行情")
        return df
        
    except Exception as e:
        logger.error(f"[tdx] 获取行情失败: {e}")
        TdxConnectionPool.close()  # 出错时重置连接
        return pd.DataFrame()
```

---

## 四、建议

1. **先测试**：用上面的测试脚本验证当前 `get_bond_tdx` 是否真的1分钟才变一次价格。

2. **如果确实有问题**：
   - 检查是否用了 `close` 而不是 `price` 字段
   - 尝试强制短连接（方案A）
   - 或者换 TDX 服务器

3. **如果当前已实现3秒级**：无需修改，直接可用。

请先用测试脚本验证，告诉我结果，我再确定是否需要修改。
