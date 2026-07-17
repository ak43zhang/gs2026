# 买点候选系统 v4 — 纯前端股债联合筛选

> 版本: v4 | 日期: 2026-05-18 | 状态: 实施中

## 1. 概述

买点候选系统基于页面已加载的大盘数据、股票/债券/行业上攻排行，纯前端完成条件评估和候选筛选。

**核心特性：**
- 零额外 API 请求（复用已有排行接口数据）
- 时间轴自动联动（数据刷新即重新筛选）
- 股债共振检测（股票排行已含 `bond_code` 字段，直接匹配债券排行）
- 可扩展条件引擎（配置数组，新增条件只需加一个对象）

## 2. 数据来源

| 数据 | API | 前端缓存变量 | 关键字段 |
|------|-----|-------------|---------|
| 大盘概览 | `/api/monitor/market-overview` | `_mktData` | body_up, cur_up, min_up, min_down, strength_score |
| 股票排行 | `/api/monitor/attack-ranking/stock` | `_stockRank` | code, name, change_pct, cumulative_main_net, max_cumulative_main_net, **bond_code**, bond_name, industry_name |
| 债券排行 | `/api/monitor/attack-ranking/bond` | `_bondRank` | code, name, change_pct, cumulative_main_net, max_cumulative_main_net, industry_name |
| 行业排行 | `/api/monitor/attack-ranking/industry` | `_industryRank` | name, count |

**关键发现：** 股票排行经 `_enrich_stock_data()` 处理后已包含 `bond_code` / `bond_name` / `industry_name`，无需额外加载映射表。

## 3. 股债关联机制

```
股票排行.bond_code ──→ Set(_bondRank.map(b => b.code)) 中查找
                       ↓
                  匹配成功 → 股债共振（⭐⭐⭐）
                  匹配失败 → 仅股强（⭐）
```

**性能：** 构建 bondSet O(m)，查找 O(1)。无 JOIN、无二次查询。

## 4. 条件引擎

### 4.1 条件配置数组 `BP_CONDITIONS`

每个条件自包含：`id, type, name, on(默认开关), param(参数名), def(默认值), fn(检查函数)`

**条件分三类：**

| type | 说明 | 评估对象 |
|------|------|---------|
| `market` | 大盘条件 | `_mktData.stock` |
| `stock` | 个股条件 | 每条股票排行记录 |
| `link` | 联动条件 | 股票记录 + 关联债券数据 |

### 4.2 内置条件

**大盘条件（3个）：**
- `body_gt_cur` — 红柱 > 涨家数
- `tick_ratio` — tick涨跌比 > 阈值（默认 1.0）
- `strength` — 市场强度 > 阈值（默认 50，默认关闭）

**个股条件（3个）：**
- `net_ratio` — 主力净额/峰值 > 阈值（默认 0.9）
- `change_pct` — 涨幅 > 阈值（默认 2%，默认关闭）
- `in_top_ind` — 所属行业在排行前N（默认 10）

**联动条件（3个）：**
- `bond_in_rank` — 关联债券出现在债券排行中（核心共振条件）
- `bond_net` — 债券主力净额/峰值 > 阈值（默认 0.9，默认关闭）
- `bond_chg` — 债券涨幅 > 阈值（默认 2%，默认关闭）

### 4.3 扩展方式

```javascript
// 新增一个条件，只需加一个对象：
BP_CONDITIONS.push({
    id: 'new_cond', type: 'stock', name: '新条件', on: true,
    param: 'new_param', def: 50,
    fn: function(row, p, ctx) { return row.some_field > p; }
});
```

## 5. 评估流程

```
数据更新 → runBuyPoints()
              ├─ 1. 构建上下文 ctx          O(m+k)
              │     bondSet = Set(债券codes)
              │     bondMap = {code → data}
              │     topInd = Set(行业前N名)
              ├─ 2. 大盘条件评估             O(c_market)
              │     遍历 market 类条件
              ├─ 3. 逐股评估                 O(n × c_stock)
              │     遍历 stock+link 类条件
              │     计算 score + level
              ├─ 4. 排序 (level↓, score↓)    O(n log n)
              └─ 5. 渲染前30                 O(1)
```

**总复杂度：** O(n × c)，n ≈ 排行数（几十到几百），c ≈ 条件数（≤9），< 1ms。

## 6. 候选分级

| 等级 | 条件 | 说明 |
|------|------|------|
| ⭐⭐⭐ | 个股条件通过 + 债券在排行 + 债券条件通过 | 股债共振 |
| ⭐⭐ | 个股条件通过 + 债券在排行 | 股强债跟 |
| ⭐ | 个股条件通过，无关联债券或不在排行 | 仅股强 |

## 7. 触发时机

| 事件 | 动作 |
|------|------|
| 大盘数据加载/刷新 | `_mktData = data; runBuyPoints();` |
| 股票排行加载/刷新 | `_stockRank = data; runBuyPoints();` |
| 债券排行加载/刷新 | `_bondRank = data; runBuyPoints();` |
| 行业排行加载/刷新 | `_industryRank = data; runBuyPoints();` |
| 保存条件 | `saveParams(); runBuyPoints();` |
| 时间轴切换 | 排行数据自动更新 → 上述触发 |

## 8. 条件配置持久化

- 存储位置：`localStorage` key = `buyPointsConfig`
- 保存内容：各条件的 `on/off` 状态 + 参数值
- 加载时机：页面初始化时读取，合并到 `BP_CONDITIONS`

## 9. 前端展示

```
┌──────────────────────────────────────────────────┐
│ 🎯 买点候选（5只）          大盘: ✅积极 2/2通过  │
├──────────────────────────────────────────────────┤
│ ⭐⭐⭐ 300608 思创医惠  +3.2% │ 债128608 +1.8%   │
│ ⭐⭐⭐ 002475 立讯精密  +2.5% │ 债128136 +1.2%   │
│ ⭐⭐  600519 贵州茅台  +1.8% │ 债在榜            │
│ ⭐   000858 五粮液    +2.1% │ 无关联债           │
└──────────────────────────────────────────────────┘
```

## 10. 改动清单

| 模块 | 说明 |
|------|------|
| 删除后端 `/buy-points` 路由 | 不再需要独立 API |
| 删除旧前端 fetch + 渲染代码 | 清理旧逻辑 |
| 新增 `BP_CONDITIONS` 配置数组 | 可扩展条件定义 |
| 新增 `runBuyPoints()` | 纯前端评估引擎 |
| 新增 `renderBpResult()` | 星级 + 债券信息渲染 |
| 新增条件编辑面板（3类分组） | HTML + JS |
| 4处数据回调添加缓存 + 触发 | 每处2行 |

## 11. 依赖关系

- `_enrich_stock_data()` 必须为股票排行添加 `bond_code` / `bond_name`（已实现）
- `_enrich_bond_data()` 必须为债券排行添加 `change_pct` / `industry_name`（已实现）
- 无新增后端依赖
