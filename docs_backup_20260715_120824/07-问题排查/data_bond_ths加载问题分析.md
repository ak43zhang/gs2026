# data_bond_ths 加载问题分析报告

## 问题概述

股债联动监控脚本 `monitor_gp_zq_rising_signal.py` 报错：
```
TypeError: 'NoneType' object is not subscriptable
mid_df['stock_code'] = mid_df['stock_code'].astype(str).str.zfill(6)
```

## 根本原因

### 1. 数据加载方式变更

**旧方式（直接Redis）：**
- `redis_util.py` 主程序会执行 `mysql2redis_generate_dict("data_bond_ths", ...)`
- 将 `data_bond_ths` 表数据写入 Redis key `dict:data_bond_ths`
- 监控脚本通过 `redis_util.get_dict("data_bond_ths")` 读取

**新方式（缓存预热）：**
- 新增了 `dashboard2/cache/` 缓存管理器
- 使用 `stock_bond_mapping_cache.py` 管理映射关系
- 数据写入 Redis key `stock_bond_mapping:{date}`（Hash结构）
- **不再写入** `dict:data_bond_ths`

### 2. 问题定位

| 组件 | 写入Key | 读取Key | 状态 |
|------|---------|---------|------|
| redis_util.py (main) | `dict:data_bond_ths` | - | 不再执行 |
| stock_bond_mapping_cache.py | `stock_bond_mapping:{date}` | - | 新方式 |
| monitor_gp_zq_rising_signal.py | - | `dict:data_bond_ths` | **读取失败** |

### 3. 缓存预热流程

```
dashboard2/app.py 启动
    ↓
init_all_caches() 注册缓存
    ↓
stock_bond_mapping.warmup_stock_bond_mapping()
    ↓
StockBondMappingCache.update_mapping()
    ↓
写入 Redis: stock_bond_mapping:2026-04-07 (Hash)
```

**注意：** 缓存预热是异步执行的，可能在监控脚本启动时还未完成。

## 修复方案

### 方案1：监控脚本适配新缓存（推荐）

修改 `monitor_gp_zq_rising_signal.py`，使用新的缓存方式：

```python
# 旧方式（失效）
mid_df = redis_util.get_dict("data_bond_ths")

# 新方式
from gs2026.utils.stock_bond_mapping_cache import get_cache
cache = get_cache()
mid_df = cache.get_all_mapping_as_dataframe()  # 需要新增方法
```

### 方案2：恢复旧的数据加载

在缓存预热中添加 `dict:data_bond_ths` 的写入：

```python
# 在 stock_bond_mapping_cache.py 的 update_mapping 方法中添加
from gs2026.utils import redis_util
redis_util.mysql2redis_generate_dict("data_bond_ths", 
    '债券代码 as code,债券简称 as name,正股代码 as stock_code')
```

### 方案3：双写兼容（已实施）

保持现有的空值检查和运行时重试，同时逐步迁移到新缓存：

```python
# 已实施的修复
global mid_df
if mid_df is None or mid_df.empty:
    mid_df = redis_util.get_dict("data_bond_ths")
    if mid_df is None or mid_df.empty:
        # 尝试从新缓存获取
        from gs2026.utils.stock_bond_mapping_cache import get_cache
        cache = get_cache()
        if cache.is_cache_valid():
            mappings = cache.get_all_mapping()
            mid_df = pd.DataFrame.from_dict(mappings, orient='index')
```

## 当前状态

- ✅ 已添加空值检查，避免 TypeError
- ✅ 已添加运行时重试机制
- ⚠️ 需要长期方案确保数据一致性

## 建议

1. **短期**：保持当前修复（空值检查+重试）
2. **中期**：统一使用 `stock_bond_mapping_cache` 新缓存
3. **长期**：移除对 `dict:data_bond_ths` 的依赖

---

**分析时间：** 2026-04-07  
**分析人：** AI Assistant
