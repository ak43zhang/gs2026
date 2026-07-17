# Dashboard2 字段规范文档

## 文档信息

- **版本**: v1.0
- **日期**: 2026-05-13
- **模块**: dashboard2 监控模块
- **相关文件**:
  - `src/gs2026/dashboard2/routes/monitor.py` - 后端数据接口
  - `src/gs2026/dashboard2/templates/monitor.html` - 前端展示
  - `src/gs2026/monitor/monitor_stock.py` - 数据计算脚本

---

## 一、股票排行数据字段

### 1.1 基础字段（固定列）

| 字段名 | 类型 | 说明 | 数据来源 | 示例值 |
|--------|------|------|----------|--------|
| `#` | string | 排名序号 | 前端生成 | `1`, `2`, `3` |
| `code` | string | 股票代码（6位，前补0） | 数据库 | `301396` |
| `name` | string | 股票名称 | 数据库 | `某股票名称` |

### 1.2 核心数据字段

| 字段名 | 类型 | 单位 | 说明 | 数据来源 | 计算逻辑 |
|--------|------|------|------|----------|----------|
| `change_pct` | float | % | 涨跌幅 | monitor_gp_sssj 表 | 实时行情数据 |
| `count` | int | 次 | 上攻次数 | monitor_gp_top30 表 | 当日累计上攻次数 |
| `main_net_amount` | float | 元 | 主力净额（累计） | monitor_gp_sssj.cumulative_main_net | 当日累计主力净流入 |
| `bond_code` | string | - | 对应债券代码 | 缓存映射 | 通过正股-债券映射获取 |
| `bond_name` | string | - | 对应债券名称 | 缓存映射 | 通过正股-债券映射获取 |
| `industry` / `industry_name` | string | - | 所属行业 | 缓存映射 | 通过股票-行业映射获取 |

### 1.3 派生字段（Derived Fields）

| 字段名 | 类型 | 单位 | 说明 | 数据来源 | 计算逻辑 |
|--------|------|------|------|----------|----------|
| `consecutive_attacks` | int | 次 | 连续上攻次数 | monitor_gp_sssj 表 | 连续出现主力净流入的时段数 |
| `main_net_count` | int | 次 | 净额次数 | monitor_gp_sssj 表 | 当日累计有主力净额的次数 |
| `max_cumulative_main_net` | float | 元 | 峰值净额（当日最高累计值） | monitor_gp_sssj 表 | 当日累计主力净额的最大值 |

---

## 二、派生字段详细计算逻辑

### 2.1 consecutive_attacks（连续上攻次数）

**定义**: 股票连续出现主力净流入的时段数量

**计算逻辑**（monitor_stock.py）:
```python
# 判断当前时段是否有主力净额
has_main_net = (df_now['main_net_amount'].abs() > 1e-6).astype(int)

# 如果有上一时段数据
if 'consecutive_attacks' in df_prev_main.columns:
    # 连续：上一时段连续次数 + 1
    # 中断：重置为 0 或 1（根据当前是否有净额）
    df_now['consecutive_attacks'] = df_now['consecutive_attacks_prev'] * has_main_net + has_main_net
else:
    # 首次：当前有主力净额则为 1，否则为 0
    df_now['consecutive_attacks'] = has_main_net
```

**示例**:
- 时段1: 有净额 → consecutive_attacks = 1
- 时段2: 有净额 → consecutive_attacks = 2
- 时段3: 无净额 → consecutive_attacks = 0
- 时段4: 有净额 → consecutive_attacks = 1（重新计数）

---

### 2.2 main_net_count（净额次数）

**定义**: 当日累计出现主力净额的次数

**计算逻辑**（monitor_stock.py）:
```python
# 判断当前时段是否有主力净额（绝对值 > 0.000001）
has_main_net = (df_now['main_net_amount'].abs() > 1e-6).astype(int)

# 如果有上一时段数据
if 'main_net_count' in df_prev_main.columns:
    # 累加：上一时段次数 + 当前时段是否有净额
    df_now['main_net_count'] = df_now['main_net_count_prev'] + has_main_net
else:
    # 首次：当前有主力净额则为 1，否则为 0
    df_now['main_net_count'] = has_main_net
```

**与 count（上攻次数）的区别**:
- `count`: 上攻次数（价格异动）
- `main_net_count`: 有主力净额出现的次数

---

### 2.3 max_cumulative_main_net（峰值净额）

**定义**: 当日累计主力净额的最大值（历史峰值）

**计算逻辑**（monitor_stock.py 第 717-736 行）:
```python
# 如果有上一时段数据
if 'max_cumulative_main_net' in df_prev_main.columns:
    prev_max = df_prev_main[['stock_code', 'max_cumulative_main_net']].copy()
    
    if not prev_max.empty:
        prev_max['stock_code'] = prev_max['stock_code'].astype(str).str.strip().str.zfill(6)
        
        # 合并上一时段的峰值数据
        df_now = df_now.merge(
            prev_max,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 历史峰值 vs 当前累计值，取大者
        df_now['max_cumulative_main_net_prev'] = df_now['max_cumulative_main_net_prev'].fillna(0)
        df_now['max_cumulative_main_net'] = df_now[['max_cumulative_main_net_prev', 'cumulative_main_net']].max(axis=1)
else:
    # 首次：直接取当前累计值
    df_now['max_cumulative_main_net'] = df_now['cumulative_main_net']
```

**关键说明**:
- `max_cumulative_main_net` 是**历史峰值**，只增不减
- `cumulative_main_net` 是**当前累计值**，可能回落
- 两者差值反映资金流出程度

---

## 三、前端展示字段

### 3.1 股票排行表格列配置

**列定义**（monitor.html STOCK_COLUMNS）:

```javascript
const STOCK_COLUMNS = [
    // 固定列
    { key: '#',       label: '#',       fixed: true },
    { key: 'code',    label: '代码',    fixed: true },
    { key: 'name',    label: '名称',    fixed: true },
    
    // 可选列
    { key: 'change_pct',      label: '涨跌幅',   sortable: true, default: true },
    { key: 'count',           label: '次数',     sortable: true, default: true },
    { key: 'main_net_amount', label: '主力净额',  sortable: true, default: true },
    { key: 'bond_code',       label: '债券代码',  sortable: true, default: true },
    { key: 'bond_name',       label: '债券名称',  sortable: false, default: true },
    { key: 'industry',        label: '行业',     sortable: true, default: true },
    
    // 派生字段
    { key: 'consecutive_attacks', label: '连续上攻', sortable: true, default: true },
    { key: 'main_net_count',      label: '净额次数', sortable: true, default: true },
    { key: 'max_cumulative_main_net', label: '峰值净额', sortable: true, default: false },
];
```

### 3.2 峰值净额列展示逻辑

**当前实现**（monitor.html 第 1349-1375 行）:

```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;  // ⚠️ Bug: 字段名不匹配
    const peak = item.max_cumulative_main_net || 0;
    
    if (peak === 0) return '<td>-</td>';
    
    // 计算回落百分比
    const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
    const isDropping = current < peak * 0.8; // 回落超过20%
    
    let colorClass = '';
    let indicator = '';
    
    if (isDropping) {
        colorClass = 'peak-warning';  // 回落超过20%，红色警告
        indicator = '↓';
    } else if (current >= peak * 0.95) {
        colorClass = 'peak-strong';   // 保持在峰值95%以上，绿色强势
        indicator = '→';
    }
    
    const peakStr = formatMoney(peak);
    
    return `<td class="${colorClass}">
        <div class="peak-value">${peakStr} ${indicator}</div>
        <div class="drop-pct small">${dropPct}%</div>
    </td>`;
}
```

**展示说明**:
- **峰值数值**: 显示 `max_cumulative_main_net` 的值（当日最高累计主力净额）
- **回落百分比**: 计算 `(峰值 - 当前) / 峰值 * 100%`
- **状态指示**:
  - `↓` 红色: 当前累计值 < 峰值 × 80%（回落超过20%）
  - `→` 绿色: 当前累计值 ≥ 峰值 × 95%（保持强势）
  - 无标记: 介于两者之间

---

## 四、数据流转图

```
┌─────────────────────────────────────────────────────────────────┐
│                     数据源（Data Sources）                         │
├─────────────────────────────────────────────────────────────────┤
│  monitor_gp_sssj_YYYYMMDD 表（实时数据）                          │
│  - stock_code: 股票代码                                          │
│  - change_pct: 涨跌幅                                            │
│  - main_net_amount: 单时段主力净额                                │
│  - cumulative_main_net: 累计主力净额 ⭐                          │
│  - consecutive_attacks: 连续上攻次数                              │
│  - main_net_count: 净额次数                                      │
│  - max_cumulative_main_net: 峰值净额 ⭐                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     数据服务层（Data Service）                     │
├─────────────────────────────────────────────────────────────────┤
│  DataService.get_stock_ranking()                                 │
│  DataService.get_ranking_at_time()                               │
│  - 从 Redis/MySQL 获取原始数据                                    │
│  - 返回基础字段（code, name, count...）                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     数据增强层（Enrichment）                      │
├─────────────────────────────────────────────────────────────────┤
│  _enrich_change_pct_and_main_net()                             │
│  _get_change_pct_and_main_net_batch()                          │
│  - 批量获取 change_pct                                          │
│  - 批量获取 main_net_amount（来自 cumulative_main_net）           │
│  - 批量获取派生字段（consecutive_attacks, main_net_count,         │
│                     max_cumulative_main_net）                    │
│  - 填充到 stock 对象                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API 响应（JSON Response）                     │
├─────────────────────────────────────────────────────────────────┤
│  {                                                               │
│    "success": true,                                              │
│    "data": [                                                     │
│      {                                                           │
│        "code": "301396",                                         │
│        "name": "某股票",                                          │
│        "change_pct": 2.5,                                        │
│        "count": 5,                                               │
│        "main_net_amount": -2481000,  // 当前累计值 ⭐            │
│        "max_cumulative_main_net": 661000,  // 峰值 ⭐             │
│        "consecutive_attacks": 3,                                 │
│        "main_net_count": 8,                                      │
│        ...                                                       │
│      }                                                           │
│    ]                                                             │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     前端展示（Frontend）                          │
├─────────────────────────────────────────────────────────────────┤
│  峰值净额列渲染逻辑：                                              │
│  - current = item.cumulative_main_net || 0  // ⚠️ 字段缺失        │
│  - peak = item.max_cumulative_main_net || 0                      │
│  - dropPct = ((peak - current) / peak * 100).toFixed(1)          │
│  - 显示：峰值数值 + 状态指示 + 回落百分比                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、Bug 分析：峰值净额显示 100% 问题

### 5.1 问题描述

以股票 `301396` 为例：
- 前端显示"主力资金": -248.1万（实际是当前累计值）
- 峰值净额: 66.1万
- 回落百分比: **100%** ← 错误！

### 5.2 问题根源

**后端数据字段**:
```python
# monitor.py 第 417-418 行
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
# ❌ 缺少: stock['cumulative_main_net'] = main_net
```

**前端期望字段**:
```javascript
// monitor.html 第 1350 行
const current = item.cumulative_main_net || 0;  // ❌ 实际为 undefined
const peak = item.max_cumulative_main_net || 0;  // ✓ 66.1万

// 计算结果
dropPct = (661000 - 0) / 661000 * 100 = 100%
```

### 5.3 修复方案

**方案一：后端添加字段**（推荐）

在 `monitor.py` 第 417-418 行后添加：
```python
# 主力净额（已从cumulative_main_net或main_net_amount获取）
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
stock['cumulative_main_net'] = main_net if main_net is not None else 0  // 新增
```

**方案二：前端修改字段名**

将 `monitor.html` 第 1350 行：
```javascript
const current = item.cumulative_main_net || 0;
```
改为：
```javascript
const current = item.main_net_amount || 0;
```

---

## 六、数据库表结构

### 6.1 monitor_gp_sssj_YYYYMMDD 表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | varchar(6) | 股票代码 |
| time | time | 时间戳 |
| change_pct | decimal(10,4) | 涨跌幅(%) |
| main_net_amount | decimal(20,4) | 单时段主力净额 |
| **cumulative_main_net** | decimal(20,4) | **累计主力净额** |
| **consecutive_attacks** | int | **连续上攻次数** |
| **main_net_count** | int | **净额次数** |
| **max_cumulative_main_net** | decimal(20,4) | **峰值净额** |

### 6.2 字段关系说明

```
单时段数据（每3秒）:
├── main_net_amount: 该时段的主力净流入（可能为正/负/零）
└── change_pct: 该时段的涨跌幅

累计数据（当日累计）:
├── cumulative_main_net: Σ(main_net_amount) 从开盘到当前
├── main_net_count: count(main_net_amount ≠ 0) 从开盘到当前
├── consecutive_attacks: 连续有净额的时段数
└── max_cumulative_main_net: max(cumulative_main_net) 从开盘到当前
```

---

## 七、附录

### 7.1 相关代码文件清单

| 文件路径 | 说明 |
|----------|------|
| `src/gs2026/dashboard2/routes/monitor.py` | 监控数据API路由 |
| `src/gs2026/dashboard2/templates/monitor.html` | 监控页面模板 |
| `src/gs2026/monitor/monitor_stock.py` | 股票监控数据计算脚本 |
| `src/gs2026/dashboard/services/data_service.py` | 数据服务层 |

### 7.2 术语表

| 术语 | 说明 |
|------|------|
| 主力净额 | 大单净流入金额，反映主力资金动向 |
| 累计主力净额 | 当日从开盘到当前时段的主力净额总和 |
| 峰值净额 | 当日累计主力净额的最大值（历史最高） |
| 回落百分比 | (峰值 - 当前) / 峰值 × 100%，反映资金流出程度 |
| 上攻 | 价格快速上涨并伴随成交量放大 |
| 连续上攻 | 连续多个时段出现主力净流入 |

---

*文档结束*
