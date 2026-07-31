# 上攻排行「仅前N区间次数」过滤 - 设计方案（债券 + 股票）

## 需求（已确认）

在**债券**和**股票**上攻排行的过滤面板中，各新增「仅前N区间次数」过滤条件，逻辑与现有「仅前N金额」一致，排序依据用 `window_count`（区间次数）。

N 选项：**全部 / 5 / 10**（默认"全部"）。

---

## 一、现状分析（现有「仅前N金额」实现）

**文件**：`src/gs2026/dashboard2/templates/monitor.html`（纯前端过滤，无后端改动）

**数据字段**：债券数据已含 `window_count`（列名"区间次数"，BOND_COLUMNS 第2376行），与 `amount` 平级，无需后端改动。

**现有金额过滤的4个关键点**：

| 环节 | 位置 | 说明 |
|------|------|------|
| ① 配置 | `BOND_FILTERS` 数组（~3208行）| `topn_amount` 项，type=select |
| ② 状态变量 | `_bondTopNAmountVal='30'`（~3296行）| 跟踪当前选值 |
| ③ 过滤函数 | `filterBondByTopNAmount(data)`（~3310行）| 从全量数据取前N金额的code |
| ④ 调用链 | `rerenderBondRanking()`（~3336行）| 过滤管道中调用 |
| ⑤ 徽章统计 | `updateBondFilterBadge()`（~3279行）| 值≠0时计入激活数 |

**过滤逻辑核心**（金额版）：
```javascript
function filterBondByTopNAmount(data) {
    var el = document.getElementById('bond-topn-amount');
    if (!el) return data;
    _bondTopNAmountVal = el.value;
    var n = parseInt(el.value) || 0;
    if (n <= 0 || data.length <= n) return data;
    // 始终从全量原始数据取前N金额的code
    var raw = window._bondRankRawData || data;
    var sorted = raw.slice().sort((a,b) => (parseFloat(b.amount)||0) - (parseFloat(a.amount)||0));
    var topNCodes = {};
    for (var i = 0; i < Math.min(n, sorted.length); i++) topNCodes[sorted[i].code] = true;
    return data.filter(item => topNCodes[item.code]);
}
```

---

## 二、设计方案（新增「仅前N区间次数」）

完全复刻金额过滤的模式，5处对应改动：

### ① 新增配置项（BOND_FILTERS 数组）
在 `topn_amount` 之后插入：
```javascript
{
    key: 'topn_window',
    label: '仅前N区间次数',
    type: 'select',
    selectId: 'bond-topn-window',
    options: [
        { value: '0',  label: '全部', default: true },
        { value: '5',  label: '5' },
        { value: '10', label: '10' },
    ],
    onChange: 'rerenderBondRanking()',
},
```

### ② 新增状态变量
```javascript
let _bondTopNWindowVal = '0';  // 默认全部
```

### ③ 新增过滤函数
```javascript
// 仅前N区间次数筛选（始终基于全量原始数据）
function filterBondByTopNWindow(data) {
    var el = document.getElementById('bond-topn-window');
    if (!el) return data;
    _bondTopNWindowVal = el.value;
    var n = parseInt(el.value) || 0;
    if (n <= 0 || data.length <= n) return data;
    var raw = window._bondRankRawData || data;
    var sorted = raw.slice().sort(function(a, b) {
        return (parseFloat(b.window_count) || 0) - (parseFloat(a.window_count) || 0);
    });
    var topNCodes = {};
    for (var i = 0; i < Math.min(n, sorted.length); i++) { topNCodes[sorted[i].code] = true; }
    return data.filter(function(item) { return topNCodes[item.code]; });
}
```

### ④ 接入过滤管道（rerenderBondRanking）
在 `filterBondByTopNAmount` 之后加一行：
```javascript
filtered = filterBondByTopNAmount(filtered);
filtered = filterBondByTopNWindow(filtered);   // 新增
filtered = filterBondByGreenList(filtered);
```

### ⑤ 徽章统计（updateBondFilterBadge）
```javascript
const windowEl = document.getElementById('bond-topn-window');
if (windowEl && windowEl.value !== '0') activeCount++;
```

---

## 五、股票上攻排行同步改动

股票数据同样含 `window_count`（STOCK_COLUMNS 第2233行"区间次数"）。股票过滤面板结构略有不同（用独立变量，无 select 型过滤），改动5处：

### ① 新增配置项（STOCK_FILTERS 数组，~3347行）
在 `topn_industry` 之后插入（与债券选项一致）：
```javascript
{
    key: 'topn_window',
    label: '仅前N区间次数',
    type: 'select',
    selectId: 'stock-topn-window',
    options: [
        { value: '0',  label: '全部', default: true },
        { value: '5',  label: '5' },
        { value: '10', label: '10' },
    ],
    onChange: 'rerenderStockRanking()',
},
```

### ② 渲染面板支持 select 类型（renderStockFilterPanel，~3393行）
股票面板当前**没有** select 分支，需补上（复用债券的 select 渲染逻辑）：
```javascript
} else if (f.type === 'select') {
    const curVal = _stockTopNWindowVal || '0';
    html += `<label>${f.label}</label>`;
    html += `<select id="${f.selectId}" onchange="${f.onChange}">`;
    f.options.forEach(opt => {
        const sel = curVal === opt.value ? 'selected' : '';
        html += `<option value="${opt.value}" ${sel}>${opt.label}</option>`;
    });
    html += `</select>`;
}
```

### ③ 新增状态变量 + 过滤函数
```javascript
let _stockTopNWindowVal = '0';

function filterStockByTopNWindow(data) {
    var el = document.getElementById('stock-topn-window');
    if (!el) return data;
    _stockTopNWindowVal = el.value;
    var n = parseInt(el.value) || 0;
    if (n <= 0 || data.length <= n) return data;
    var raw = _rankRawData['stock-ranking'] || data;
    var sorted = raw.slice().sort(function(a, b) {
        return (parseFloat(b.window_count) || 0) - (parseFloat(a.window_count) || 0);
    });
    var topNCodes = {};
    for (var i = 0; i < Math.min(n, sorted.length); i++) { topNCodes[sorted[i].code] = true; }
    return data.filter(function(item) { return topNCodes[item.code]; });
}
```

### ④ 接入过滤管道（rerenderStockRanking，~3181行）
```javascript
filtered = filterStockByTopNSectors(filtered);
filtered = filterStockByTopNWindow(filtered);   // 新增
filtered = filterStockByBond(filtered);
```

### ⑤ 徽章统计（updateStockFilterBadge，~3419行）
```javascript
const windowEl = document.getElementById('stock-topn-window');
if (windowEl && windowEl.value !== '0') activeCount++;
```

---

## 七、关键设计决策

| 项 | 决策 | 理由 |
|----|------|------|
| **纯前端** | 无后端改动 | `window_count` 已在债券/股票数据中 |
| **默认值** | 全部（value='0'）| 符合需求，不影响现有行为 |
| **过滤基准** | 全量原始数据（bond用`_bondRankRawData`，stock用`_rankRawData['stock-ranking']`）| 与金额过滤一致，避免受其他过滤影响 |
| **排序字段** | `window_count` | 对应"区间次数" |
| **组合过滤** | 可与金额/行业/转债模式/绿名单叠加 | 取交集（都在管道中串行过滤）|
| **selectId** | `bond-topn-window` / `stock-topn-window` | 命名与 `*-topn-amount` 对齐 |

---

## 八、组合过滤行为说明

多个过滤条件**取交集**（串行过滤）。例如：
- 「仅前10金额」+「仅前5区间次数」
- = 先筛出金额前10的code，再从中筛出区间次数前5的code
- = 同时满足两个条件的债券

这与现有「金额+行业+绿名单」的叠加行为一致。

---

## 九、影响范围与风险

| 项 | 评估 |
|----|------|
| **改动文件** | 仅 `monitor.html`（1个文件）|
| **改动处** | 债券5处 + 股票5处 = 10处 |
| **后端** | 无改动 |
| **数据库** | 无改动 |
| **现有功能** | 无破坏（纯新增，默认"全部"不生效）|
| **风险等级** | 低 |

---

## 十、已确认

1. ✅ N选项：**全部 / 5 / 10**（默认"全部"）
2. ✅ 债券 + 股票**都加**

审核通过后实施。

