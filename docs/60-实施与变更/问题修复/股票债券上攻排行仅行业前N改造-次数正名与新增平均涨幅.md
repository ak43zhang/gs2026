# 股票债券上攻排行仅行业前N改造-次数正名与新增平均涨幅

> 文档路径：`docs/60-实施与变更/问题修复/股票债券上攻排行仅行业前N改造-次数正名与新增平均涨幅.md`
> 目标文件（前端）：`src/gs2026/dashboard2/templates/monitor.html`
> 目标文件（后端）：`src/gs2026/dashboard2/routes/monitor.py`、`src/gs2026/dashboard/services/data_service.py`

---

## 版本控制记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-08-01 | 助手 | 初稿：现状分析、需求拆解、改造方案设计 |
| v1.1 | 2026-08-01 | 助手 | 确认实施细节（命名/选项/降序/可同时启用），进入实施 |
| v1.2 | 2026-08-01 | 助手 | 实施完成，前后端自测通过，已提交 |
| v1.3 | 2026-08-01 | 助手 | 发现数据一致性问题：涨幅前N与行业上攻排行对不上。根因定位 + 口径决策（静态字段全市场/动态字段上攻排行）+ 修复A（接口支持time） |
| v1.4 | 2026-08-01 | 助手 | 修复A实施完成：路由读time、get_industry_ranking支持time_str、sort_by=avg_change_pct时查monitor_hy_top30表该时点全量按涨幅排，验证通过 |

---

## 【v1.3 补充】数据一致性问题排查与口径决策

### 问题现象
分析时间点 09:30:54，股票上攻排行开启"仅行业涨幅前10"后保留了 300663（行业=软件开发）；但行业上攻排行按平均涨幅降序却看不到软件开发。两处对不上。

### 根因（实测 20260731 数据确认）
**根因1：数据范围不一致（核心）**
- 行业上攻排行：请求 `/attack-ranking/industry`，后端默认 `limit=30`，**按次数(count)降序**返回前30个行业；前端点"平均涨幅"列排序仅对这30条重排
- 仅行业涨幅前10：走 `get_industry_ranking(sort_by=avg_change_pct)`，取**全量90个行业**按涨幅降序取前10
- 实测：软件开发按 count 排**第69位**（count=69），远在前30外 → 行业上攻排行30条里没有它 → 前端按涨幅列排序也看不到；但其涨幅 6.14% 全市场第1 → 在"涨幅前10"里 → 300663 被保留

**根因2：行业接口忽略 time 参数（真 bug）**
- `/attack-ranking/industry` 路由只读 date/limit/sort_by，**未读 time**
- 导致"涨幅前N"即使传 `&time=09:30:54` 也被忽略，返回**最新/收盘**全量涨幅榜，非选中时点

### 口径决策（用户确认）
**按字段性质区分数据口径：**
- **平均涨幅 = 静态字段**（某时点的涨幅快照）→ 基于**全市场90行业涨幅榜**（保持方向2）
- **次数 = 动态字段**（随时间累积，反映上攻持续性）→ 基于**行业上攻排行**（现状）

因此"涨幅前N与行业上攻排行对不上"是**预期行为**（两者本就是不同视角），不需要统一口径。但**必须修复根因2**（time 被忽略），让涨幅榜使用选中时点的真实数据。

### 修复A（必须做）：行业接口支持 time 参数
1. 路由 `/attack-ranking/industry` 读取 `time` 参数并透传
2. `get_industry_ranking` 增加 `time_str` 参数
3. `sort_by=avg_change_pct` 且有 time 时：取**该时点**全市场90行业（`monitor_hy_top30` 表 time≤选定时间的最新时点全部行业），按涨幅降序取前N
4. 无 time（实时/最新）时：维持现状取最新时点

### 修复A 实施记录
- [x] 路由 get_industry_ranking 读取 time 并透传
- [x] get_industry_ranking 支持 time_str（sort_by=avg_change_pct 时取该时点全量按涨幅排）
- [x] 自测：time=09:30:54 涨幅前10 使用该时点数据（软件开发1.52%不在前10）；无time时用收盘数据（软件开发6.14%在第1）
- [x] 语法检查 + Git 提交

### 修复A 验证结果
```
time=09:30:54 涨幅前10:
  半导体 pct=7.4833
  电子化学品 pct=7.0488
  ...（软件开发不在）
软件开发在前10内: False

无time（收盘）涨幅前10:
  软件开发 pct=6.1376（第1）
  ...
软件开发在前10内: True
```
→ 修复A生效：涨幅榜现在使用选中时点的真实数据，不再用收盘数据。

---

> **本需求仅维护此单一文档，所有分析、方案、实施记录、验证结果均在此文件内按版本追加，不另建文件。**

---

## 一、需求

1. 当前股票/债券上攻排行的"仅前N行业"，实际是基于**行业次数**排名取前N行业。将其**正名为"仅行业次数前N"**，使语义贴合本意。
2. 股票/债券上攻排行**新增"仅行业涨幅前N"**：取按**行业平均涨幅（avg_change_pct）** 降序的前N行业，过滤逻辑与次数版完全相同。

### 已确认实施细节
- 命名：现有 →「仅行业次数前N」；新增 →「仅行业涨幅前N」
- N 选项：与次数版一致（全部/5/10）
- 平均涨幅排序：**降序**（涨幅最高的前N个行业）
- 两个过滤器**可同时启用**（取交集，符合现有过滤管道模型）

---

## 二、现状分析

### 当前"仅前N行业"的实现
- 股票：`updateStockTopNSectors()`，债券：`updateTopNSectors()`
- 两者都请求同一接口：`/api/monitor/attack-ranking/industry?limit=N`
- 取回 `r.data.map(item => item.name)` 作为"前N行业名单"
- 过滤：保留个股/转债中 `industry_name` 在该名单内的记录

### 该接口的行业排序基准
- 实时主路径（Redis）：`zrevrange` 按 score（**行业次数 count** 累计）降序
- 历史 MySQL：`ORDER BY rank`（按 final_score 排名）
- at-time：按 `code_counts` 次数降序

**结论**：现有"前N行业" ≈ **行业次数前N**，用户理解正确，仅命名不够点题。

### 关键数据基础
- `avg_change_pct`（行业平均涨幅）字段已在上一任务为 industry 接口的 4 条数据路径全部补充，数据现成可用。

---

## 三、改造方案

### 核心思路
后端 industry 接口**新增排序参数 `sort_by`**（`count` | `avg_change_pct`，默认 `count` 向后兼容）。前端两个过滤器分别用不同 `sort_by` 取前N行业名单，各自维护独立的名单缓存，逻辑完全对称、互不干扰。

> 为何后端排序而非前端拿全量自排：接口默认只返回排名靠前行业，前端拿不到"全部行业按涨幅排"的正确结果；且"涨幅前N"必须**先按全量排序再截断**，后端做最准。行业总数仅约90条，无性能问题。

### 一、后端

**1. 路由 `get_industry_ranking`（monitor.py）** 增加 `sort_by` 参数并透传：
```python
sort_by = request.args.get('sort_by', 'count')
data = data_service.get_industry_ranking(limit=limit, date=date, use_mysql=use_mysql, sort_by=sort_by)
```

**2. 服务层（data_service.py）** `get_industry_ranking` / `get_rising_ranking` 行业分支支持 `sort_by`：
- `sort_by='count'`：维持现状（次数降序）
- `sort_by='avg_change_pct'`：先取全量行业（含 avg_change_pct），按该字段**降序**排序，再截前 N
- 兼容：`get_ranking_at_time` 行业分支同样支持（时间轴/历史）

> 实现要点：涨幅前N必须"**先排序后截断**"，不能先按次数截断再排涨幅。

### 二、前端（monitor.html）

**股票侧：**
1. 现有控件 `stock-topn-industry`：label「仅前N行业」→「仅行业次数前N」；`updateStockTopNSectors()` 请求加 `&sort_by=count`
2. 新增控件 `stock-topn-industry-pct`（label「仅行业涨幅前N」，选项 全部/5/10）：
   - 名单缓存 `_stockTopSectorsByPct = []`
   - `updateStockTopNSectorsByPct()`：请求 `industry?limit=N&sort_by=avg_change_pct`
   - `onStockTopNIndustryPctChange()`
   - `filterStockByTopNSectorsPct(d, mode)`（逻辑同次数版，用涨幅名单）
   - `STOCK_PIPELINE` 注册 `topn_sectors_pct`（ranking 型，sortField: `industry_name`）
   - filterConfig 增加该 select，`PERSIST_CONTROLS` 增加其 id

**债券侧（对称）：**
1. 现有 `bond-topn-filter`/`bond-topn-count`：label→「仅行业次数前N」；`updateTopNSectors()` 加 `&sort_by=count`
2. 新增控件 `bond-topn-industry-pct`：名单缓存 `_topSectorsByPct`、`updateTopNSectorsByPct()`、`filterBondByTopNSectorsByPct()`、`BOND_PIPELINE` 注册、filterConfig、持久化

### 三、过滤管道语义（沿用现有引擎）
- 两个"前N行业"过滤器均为 **ranking 型**，各自基于候选池 S 算命中集合，取交集（顺序无关）
- 谓词模式：行业名存在即保留（与现有一致）
- 可同时启用：次数前N ∩ 涨幅前N（交集）

### 四、页面加载恢复
`restoreFilterState` 中，若新控件值>0，预取对应涨幅前N名单（仿现有次数版预取）。

---

## 四、影响范围与风险

- 后端：industry 接口加 `sort_by`（默认 count 向后兼容），data_service 行业分支加排序分支；不动股票/债券排行本身
- 前端：股票/债券各新增 1 个 select + 一套名单缓存/更新/过滤函数 + 管道注册 + 持久化；现有"前N行业"仅改 label + 请求加 `sort_by=count`
- 风险：低。新增与现有次数版完全对称；`avg_change_pct` 数据已就绪；沿用已验证的过滤管道引擎
- 生效：后端重启 + 前端刷新

---

## 五、实施记录

- [x] 后端路由 get_industry_ranking 加 sort_by（monitor.py）
- [x] 后端 data_service.get_industry_ranking 支持 sort_by（sort_by=avg_change_pct 时先取全量→按涨幅降序→截前N→重排rank）
- [x] 前端股票：正名「仅行业次数前N」+ updateStockTopNSectors 加 sort_by=count
- [x] 前端股票：新增「仅行业涨幅前N」（stock-topn-industry-pct + _stockTopSectorsByPct + updateStockTopNSectorsByPct + onStockTopNIndustryPctChange + filterStockByTopNSectorsPct + STOCK_PIPELINE.topn_sectors_pct + filterConfig + 持久化）
- [x] 前端债券：正名「仅行业次数前N」+ updateTopNSectors 加 sort_by=count
- [x] 前端债券：新增「仅行业涨幅前N」（bond-topn-industry-pct + _topSectorsByPct + updateBondTopNSectorsByPct + onBondTopNIndustryPctChange + filterBondByTopNSectorsByPct + BOND_PIPELINE.topn_sectors_pct + filterConfig + 持久化）
- [x] 页面加载恢复预取涨幅名单（股票+债券）
- [x] 语法检查（后端 py_compile 通过；前端 node --check 剥离Jinja通过）
- [x] 正则查重复定义（10 个关键函数均单一定义）
- [x] 自测：后端 sort_by=avg_change_pct 返回按涨幅降序前N（与 count 序不同）
- [x] Git 提交

### 后端自测结果（date=20260731, MySQL）
```
全量行业: 90 条
涨幅前5: 软件开发(6.14%) IT服务(6.10%) 自动化设备(5.35%) 文化传媒(5.21%) 影视院线(4.87%)
次数前5: 贸易 汽车服务 房地产 钢铁 医药商业
→ 两种排序结果不同，功能正确
```

### 关键实现说明
- 涨幅前N采用"**先全量排序后截断**"：`get_industry_ranking(sort_by='avg_change_pct')` 内部取 limit=0 全量，按 avg_change_pct 降序后截前N，避免"先按次数截断再排涨幅"的偏差
- 两个前N过滤器均为 ranking 型（可切谓词），可同时启用取交集，沿用现有过滤管道引擎
- 命名统一：股票/债券均为「仅行业次数前N」+「仅行业涨幅前N」

---

## 六、验证方案

1. 后端：`industry?limit=5&sort_by=count` 与 `sort_by=avg_change_pct` 返回不同排序，后者按涨幅降序
2. 前端：股票/债券各出现两个下拉——「仅行业次数前N」「仅行业涨幅前N」
3. 分别启用：次数版按行业次数筛选，涨幅版按行业涨幅筛选
4. 同时启用：结果为两者交集
5. 持久化：刷新后配置保留
6. AST：新增函数/常量无重复定义
