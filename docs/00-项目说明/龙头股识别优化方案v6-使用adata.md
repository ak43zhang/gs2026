# 龙头股识别优化方案v6 - 使用adata获取流通市值

## 背景

- ztb_day表是休市数据，不能用于实时分析
- akshare网络不稳定，需要替换为adata
- 代码需要集中管理，不要分散

## 方案设计

### 核心思路

使用 **adata** 替代 akshare 获取流通市值：
1. 流通股本：`adata.stock.info.get_stock_shares(stock_code)`
2. 最新收盘价：`adata.stock.market.east_market.get_market(stock_code)`
3. 流通市值 = 流通股本 × 最新收盘价 / 100000000（转换为亿）

### 市值阈值（最终版）

| 市值 | 龙头类型 |
|------|---------|
| >1000亿 | 权重龙头 |
| 200-1000亿 | 板块中军 |
| <200亿 | 小盘情绪龙 |

### 龙头细分逻辑

```
检查AI是否已定义龙头？
    ↓ 是
    只对该AI龙头按市值细分，其他保持原样
    ↓ 否
    按时间确定龙头（第1只），再按市值细分
    第2-3只=补涨，第4只及以后=跟风
```

### 代码结构（集中管理）

所有相关代码集中在 `anomaly_analyzer.py` 中：

```python
# ========== 龙头股市值分析工具函数（集中区域）==========

def _get_stock_market_cap_adata(stock_code: str) -> Optional[float]:
    """
    使用adata获取股票流通市值（亿）
    
    计算方式：流通股本 × 最新收盘价 / 100000000
    
    Args:
        stock_code: 股票代码
        
    Returns:
        流通市值（亿），失败返回None
    """
    ...

def _classify_leader_by_market_cap(market_cap: Optional[float]) -> str:
    """
    根据流通市值判断龙头类型
    
    阈值：
    - >1000亿：权重龙头
    - 200-1000亿：板块中军
    - <200亿：小盘情绪龙
    
    Args:
        market_cap: 流通市值（亿）
        
    Returns:
        龙头类型字符串
    """
    ...

# ========== 龙头股重新计算函数 ==========

def _recalculate_roles_by_rule(...):
    """
    基于规则重新计算role（无AI调用）
    
    逻辑：
    1. 先检查AI是否已定义龙头
    2. 如果有AI龙头，只对该龙头按市值细分，其他保持原样
    3. 如果没有AI龙头，按时间确定龙头，再按市值细分
    """
    ...

# ========== 批量更新函数 ==========

def _update_mainlines_with_role_recalc(...):
    """
    更新主线并重新计算role（带市值细分）
    """
    ...
```

## 实施步骤

1. **修改 `anomaly_analyzer.py`**
   - 添加 `_get_stock_market_cap_adata()` 函数
   - 添加 `_classify_leader_by_market_cap()` 函数
   - 修改 `_recalculate_roles_by_rule()` 使用adata获取市值
   - 确保龙头细分逻辑正确

2. **删除 `base_collection.py` 中的无用代码**
   - 删除 `stock_spot_em()` 函数
   - 删除 `get_effective_trade_date()` 函数
   - 删除 `_create_stock_spot_em_indexes()` 函数
   - 恢复 `get_base_collect()` 的正常调用

3. **测试验证**
   - 测试adata获取市值功能
   - 测试龙头细分逻辑

## 优点

1. **数据源稳定**：adata比akshare更稳定
2. **实时性**：使用最新收盘价计算，接近实时
3. **代码集中**：所有相关代码在一个文件中，便于维护
4. **无额外采集**：不需要额外采集任务，实时计算

## 注意事项

1. **性能**：每次调用adata接口会有网络延迟，建议缓存结果
2. **容错**：adata接口失败时，默认返回小盘情绪龙
3. **并发**：批量查询时注意控制并发，避免被封

## 待确认

1. 是否需要缓存市值数据？（建议缓存1天，股本变动不频繁）
2. 失败时的默认策略？（建议默认小盘情绪龙）
