# 多条件筛选买点方案设计

## 需求概述

基于数据监控展示范围内的多个条件，整体筛选确定买点信号。条件支持灵活组合，方便后续扩展。

## 当前监控数据范围

### 股票市场数据

| 维度 | 字段 | 来源 |
|------|------|------|
| 大盘指数 | 上证/深证/创业板/科创50涨跌 | `index_data` |
| 板块热度 | 行业上攻Top10 | `industry_ranking` |
| 涨跌统计 | cur_up, cur_down, cur_total, cur_ratio | `market_stats` |
| tick统计 | min_up, min_down, min_up_down_ratio | `market_stats` |
| 实体红绿柱 | body_up, body_down, body_up_down_ratio | `market_stats` |
| 市场整体强度 | strength_score, state, signal | `market_stats` |

### 个股数据（上攻排行）

| 维度 | 字段 | 来源 |
|------|------|------|
| 股票基本信息 | code, name, price, change_pct | `rising_ranking` |
| 主力资金 | main_net_amount, cumulative_main_net | `main_net` |
| 峰值净额 | max_cumulative_main_net | `derived` |
| 峰值比值 | cumulative_main_net/max_cumulative_main_net | 计算 |

### 债券/联动数据

| 维度 | 字段 | 来源 |
|------|------|------|
| 债券涨跌 | cur_up, cur_down, bond_ratio | `bond_ranking` |

## 当前条件实现计划

### Day 1 ~3：框架 + 2~3个核心条件

**条件1：红柱数量 > 上涨数量**（大盘确认）
- `body_up > cur_up * 1.2`（红柱比上涨多20%以上）
- 含义：K线实体红柱明显多于涨跌统计，说明高开低走少、上涨质量高
- 数据源：`market_stats.body_up` vs `market_stats.cur_up`

**条件2：主力净额/峰值净额 > 0.9**（个股确认）
- `cumulative_main_net / max_cumulative_main_net > 0.9`
- 含义：主力资金接近历史峰值，接近拉升末端
- 数据源：`rising_ranking.cumulative_main_net / max_cumulative_main_net`

**条件3：行业上攻排行前N名**（板块确认）
- `industry_rank <= 10`
- 含义：个股所在行业处于上攻排行前列
- 数据源：`industry_ranking`（需要先获取排行再匹配）

### Day 4~5：买点信号计算

综合上述条件，计算买点信号：

```
买点分 = 条件满足数 / 条件总数

条件1 满足 → +1
条件2 满足 → +1
条件3 满足 → +1

买点分 >= 80% → 强买信号
买点分 >= 60% → 关注
买点分 <  60% → 观望
```

## 界面设计

```
┌─────────────────────────────────────────┐
│ 📊 大盘概览                              │
│ 红柱: 2116 > 上涨: 1766 ✅              │
│ tick比: 157.67 ✅                        │
├─────────────────────────────────────────┤
│ 📊 买点候选（12只）                      │
│ ┌───────────────────────────────────┐  │
│ │ ✅ 003819  欧菲光         主峰:91% │  │
│ │ ✅ 002049  紫光国微       主峰:94% │  │
│ │ ✅ 600745  闻泰科技       主峰:88% │  │
│ │ ⚠ 000938  中芯国际       主峰:82% │  │
│ └───────────────────────────────────┘  │
│                                         │
│ ⚙ 筛选条件：[红柱>上涨][主峰>90%][行业前10] │
└─────────────────────────────────────────┘
```

## 实现方案

### 方案A：后端计算 + 前端展示（推荐）

```
前端每3秒请求
  → /api/monitor/buy-points
    → 获取大盘状态（market_stats）
    → 获取股票上攻排行（rising_ranking）
    → 获取行业上攻排行（industry_ranking）
    → 逐一评估每只股票
    → 计算买点分
    → 返回候选列表
```

**优点**：
- 计算在服务端，不占用客户端资源
- 数据一致性有保障
- 可后续加入数据持久化

**缺点**：
- 改动后端 API
- 依赖多个数据接口

### 方案B：前端计算

```
前端每3秒请求
  → /api/monitor/market-overview（大盘）
  → /api/monitor/attack-ranking/stock（个股排行）
  → /api/monitor/attack-ranking/industry（行业排行）
  → JavaScript 逐一评估
  → 生成买点列表
```

**优点**：
- 不改动后端
- 快速原型

**缺点**：
- 3个请求 × 每3秒 = 9秒一轮
- 浏览器压力大

### 方案C：增量更新 + 后端缓存

参考已实施的 `RealtimeDataCache` 方案，后端缓存所有数据，API 一次返回完整结果。

## 推荐实施顺序

| 阶段 | 内容 | 时间 |
|------|------|------|
| 第一阶段 | 方案A：后端买点计算 API + 前端展示 | 2~3天 |
| 第二阶段 | 条件可视化编辑器（增删改条件） | 1天 |
| 第三阶段 | 条件权重可配置 + 历史回测 | 2天 |

## 推荐方案A详细设计

### 新 API

```
GET /api/monitor/buy-points
```

请求参数：
- `date` (optional): 日期 YYYYMMDD，默认今天
- `threshold` (optional): 买点阈值 0~1，默认 0.8

返回数据：
```json
{
    "success": true,
    "market_ok": {
        "body_up_gt_cur_up": true,
        "tick_ratio_ok": true,
        "details": "红柱1766 > 上涨1523, tick比157.67"
    },
    "candidates": [
        {
            "code": "003819",
            "name": "欧菲光",
            "price": 12.50,
            "change_pct": 4.25,
            "main_net_amount": 8500000,
            "cumulative_main_net": 9100000,
            "max_cumulative_main_net": 10000000,
            "main_net_ratio": 0.91,
            "industry_rank": 3,
            "industry_name": "消费电子",
            "buy_score": 1.0,
            "buy_signal": "强买"
        }
    ]
}
```

### 后端路由文件

新增 `dashboard2/routes/buy_point.py`

### 前端展示

在 monitor.html 中增加"买点候选"区域（使用股票排名和行业排名现有的结构）
