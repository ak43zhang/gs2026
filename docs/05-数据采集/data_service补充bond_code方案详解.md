# data_service.py 补充 bond_code 字段方案详解

> 创建时间：2026-04-28 01:04  
> 文档版本：v1.0

---

## 1. 当前代码结构

### 1.1 get_stock_ranking 函数（当前）
```python
def get_stock_ranking(self, limit: int = 30, date: Optional[str] = None, 
                     use_mysql: bool = False) -> List[Dict[str, Any]]:
    return self.get_rising_ranking(asset_type='stock', limit=limit, date=date, use_mysql=use_mysql)
```

**问题**：直接返回 `get_rising_ranking` 结果，**不包含** `bond_code` 字段。

### 1.2 get_rising_ranking 函数返回结构
```python
{
    'code': '300346',      # 股票代码
    'name': '南大光电',     # 股票名称
    'count': 5,            # 出现次数
    'type': 'stock',
    'date': '20260427',
    'rank': 1,
    'latest_price': 51.62,  # 最新价格（可选）
    'zf_30': 1.12,         # 涨幅（可选）
    'momentum': 224.0,     # 动量（可选）
    # 缺少 bond_code 和 bond_name
}
```

---

## 2. 方案设计

### 2.1 核心思路
**从 stock_picker_service 导入 `_stock_cache`，在返回数据前补充 `bond_code` 和 `bond_name`**。

### 2.2 具体修改

#### 修改1：文件顶部添加导入
```python
# 在文件顶部（约第15行）添加
try:
    from gs2026.dashboard2.services.stock_picker_service import _stock_cache
except ImportError:
    _stock_cache = {}
```

**影响分析**：
- ✅ 使用 try-except，即使 stock_picker_service 未加载也不会报错
- ✅ 空字典 `{}` 作为降级，保证代码稳定运行
- ✅ 不影响原有功能

#### 修改2：get_stock_ranking 函数改造
```python
def get_stock_ranking(self, limit: int = 30, date: Optional[str] = None, 
                     use_mysql: bool = False) -> List[Dict[str, Any]]:
    """
    获取股票上攻排行（补充bond_code和bond_name）
    
    从 _stock_cache 获取股债映射关系，为每条记录补充债券信息。
    """
    # 1. 获取基础排行数据
    result = self.get_rising_ranking(asset_type='stock', limit=limit, date=date, use_mysql=use_mysql)
    
    # 2. 【新增】补充债券代码和名称
    if _stock_cache:
        for item in result:
            stock_code = item.get('code', '')
            if stock_code in _stock_cache:
                stock_data = _stock_cache[stock_code]
                item['bond_code'] = stock_data.get('bond_code', '-')
                item['bond_name'] = stock_data.get('bond_name', '-')
            else:
                item['bond_code'] = '-'
                item['bond_name'] = '-'
    else:
        # 缓存未加载，返回默认值
        for item in result:
            item['bond_code'] = '-'
            item['bond_name'] = '-'
    
    return result
```

**影响分析**：
- ✅ 向后兼容：原有调用方无感知
- ✅ 新增字段：`bond_code` 和 `bond_name`
- ✅ 默认值：`'-'` 表示无关联债券
- ⚠️ 性能：O(n) 遍历，n=limit(30~60)，影响极小

#### 修改3：get_ranking_at_time 函数改造（同样补充）
```python
def get_ranking_at_time(self, asset_type: str = 'stock', limit: int = 15,
                        date: Optional[str] = None, 
                        time_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取某个时间点（截止到该时间）的上攻排行
    """
    # ... 原有查询逻辑 ...
    result = []
    # ... 查询代码 ...
    
    # 【新增】如果是股票排行，补充bond_code
    if asset_type == 'stock':
        if _stock_cache:
            for item in result:
                stock_code = item.get('code', '')
                if stock_code in _stock_cache:
                    stock_data = _stock_cache[stock_code]
                    item['bond_code'] = stock_data.get('bond_code', '-')
                    item['bond_name'] = stock_data.get('bond_name', '-')
                else:
                    item['bond_code'] = '-'
                    item['bond_name'] = '-'
        else:
            for item in result:
                item['bond_code'] = '-'
                item['bond_name'] = '-'
    
    return result
```

---

## 3. 稳定性分析

### 3.1 _stock_cache 的数据来源
```python
# stock_picker_service.py 中的加载逻辑
def load_stock_cache():
    """从MySQL加载股票基础数据到内存缓存"""
    global _stock_cache, _bond_map
    
    query = """
        SELECT stock_code, stock_name, industry_name, 
               concept_codes, concept_names, 
               bond_code, bond_name, update_time
        FROM data_stock_bond_map
        WHERE update_time >= CURDATE()
    """
    # 加载到 _stock_cache
    for row in results:
        _stock_cache[row['stock_code']] = {
            'stock_name': row['stock_name'],
            'industry_name': row['industry_name'],
            'bond_code': row['bond_code'],      # ← 关键字段
            'bond_name': row['bond_name'],      # ← 关键字段
            # ...
        }
```

**稳定性评估**：
| 维度 | 评估 | 说明 |
|------|------|------|
| 数据来源 | ✅ 稳定 | MySQL `data_stock_bond_map` 表，每日更新 |
| 缓存加载 | ✅ 可靠 | 服务启动时自动加载，失败有降级 |
| 实时性 | ⚠️ 日级 | 债券映射每日更新，非实时 |
| 覆盖率 | ⚠️ 部分 | 只有可转债股票有映射，普通股票为'-' |

### 3.2 异常情况处理

| 异常情况 | 处理方案 | 结果 |
|---------|---------|------|
| _stock_cache 未加载 | 使用 try-except，降级为空字典 | 返回'-' |
| 股票代码不在缓存 | 判断 `if stock_code in _stock_cache` | 返回'-' |
| bond_code 为 None | 使用 `.get('bond_code', '-')` | 返回'-' |
| 数据库查询失败 | 不影响，独立查询 | 原数据返回 |

---

## 4. 影响范围评估

### 4.1 直接影响

| 影响点 | 评估 |
|--------|------|
| API 返回字段 | 新增 `bond_code` 和 `bond_name` |
| 前端展示 | monitor.html 可显示债券代码 |
| 性能 | 增加 O(n) 遍历，n≤60，影响<1ms |
| 兼容性 | 向后兼容，原有字段不变 |

### 4.2 调用方影响

```python
# 调用示例：原有代码无需修改
data = data_service.get_stock_ranking(limit=30)
# 现在 data[0] 包含：
# {'code': '300346', 'name': '南大光电', 'bond_code': '123XXX', 'bond_name': '南电转债', ...}
```

### 4.3 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 导入失败 | 低 | try-except 包裹 |
| 缓存为空 | 低 | 返回'-'默认值 |
| 性能下降 | 极低 | n≤60，遍历成本忽略 |
| 数据不一致 | 低 | 日级更新，业务可接受 |

---

## 5. 验证方案

### 5.1 单元测试
```python
def test_get_stock_ranking_with_bond_code():
    ds = DataService()
    result = ds.get_stock_ranking(limit=5, date='20260427', use_mysql=True)
    
    # 验证字段存在
    assert 'bond_code' in result[0]
    assert 'bond_name' in result[0]
    
    # 验证格式
    for item in result:
        assert isinstance(item['bond_code'], str)
        assert isinstance(item['bond_name'], str)
```

### 5.2 集成测试
```python
# 验证前端能正确显示
# 访问 /api/monitor/attack-ranking/stock?date=20260427
# 检查返回JSON包含 bond_code 和 bond_name
```

---

## 6. 总结

| 维度 | 评估 |
|------|------|
| 实现复杂度 | ⭐ 低（仅2处修改） |
| 稳定性 | ⭐⭐⭐ 高（多重降级保护） |
| 性能影响 | ⭐ 极低（<1ms） |
| 兼容性 | ⭐⭐⭐ 完全向后兼容 |
| 维护成本 | ⭐ 低（无额外依赖） |

**结论**：方案安全可行，建议实施。

---

确认后实施开发。
