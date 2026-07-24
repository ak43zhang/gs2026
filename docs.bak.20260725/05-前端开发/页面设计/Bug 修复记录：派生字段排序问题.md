# Bug 修复记录：派生字段排序问题

## 修复信息

- **Bug 编号**: BUG-2026-002
- **修复日期**: 2026-05-13
- **修复人**: AI Assistant
- **状态**: ✅ 已修复

---

## 问题描述

**现象**: 股票上攻排行中，以下列点击排序无反应或排序不正确：
- 连续上攻 (consecutive_attacks)
- 净额次数 (main_net_count)
- 峰值净额 (max_cumulative_main_net)

**影响范围**: 股票排行页面的排序功能

---

## 根因分析

**问题定位**: `sortRankData` 函数中缺少对三个派生字段的排序处理

**代码位置**: `src/gs2026/dashboard2/templates/monitor.html` 第 1100-1230 行

**分析**:
1. 列配置中定义了这三个字段为 `sortable: true`
2. 点击表头会触发 `toggleRankSort` 函数
3. `sortRankData` 函数只处理了以下字段：
   - `change_pct` (涨跌幅)
   - `count` (次数)
   - `main_net_amount` (主力净额)
   - `industry` (行业)
   - `bond_code` (债券代码)
4. **缺少**: `consecutive_attacks`、`main_net_count`、`max_cumulative_main_net`

---

## 修复方案

**修改文件**: `src/gs2026/dashboard2/templates/monitor.html`

**修改位置**: `sortRankData` 函数中，在 `bond_code` 排序逻辑之后添加三个排序分支

**修改内容**:

```javascript
} else if (st.field === 'consecutive_attacks') {
    // 【修复】连续上攻排序
    sorted.sort((a, b) => {
        const aVal = parseInt(a.consecutive_attacks) || 0;
        const bVal = parseInt(b.consecutive_attacks) || 0;
        if (aVal !== bVal) return (aVal - bVal) * dir;
        // 相同时按涨跌幅降序
        const aPct = parseFloat(a.change_pct) || 0;
        const bPct = parseFloat(b.change_pct) || 0;
        return bPct - aPct;
    });
} else if (st.field === 'main_net_count') {
    // 【修复】净额次数排序
    sorted.sort((a, b) => {
        const aVal = parseInt(a.main_net_count) || 0;
        const bVal = parseInt(b.main_net_count) || 0;
        if (aVal !== bVal) return (aVal - bVal) * dir;
        // 相同时按涨跌幅降序
        const aPct = parseFloat(a.change_pct) || 0;
        const bPct = parseFloat(b.change_pct) || 0;
        return bPct - aPct;
    });
} else if (st.field === 'max_cumulative_main_net') {
    // 【修复】峰值净额排序
    sorted.sort((a, b) => {
        const aVal = (a.max_cumulative_main_net !== null && a.max_cumulative_main_net !== undefined) ? parseFloat(a.max_cumulative_main_net) : null;
        const bVal = (b.max_cumulative_main_net !== null && b.max_cumulative_main_net !== undefined) ? parseFloat(b.max_cumulative_main_net) : null;
        if (aVal === null && bVal === null) return 0;
        if (aVal === null) return 1;
        if (bVal === null) return -1;
        if (aVal !== bVal) return (aVal - bVal) * dir;
        // 相同时按当前累计值降序
        const aCurrent = parseFloat(a.cumulative_main_net) || 0;
        const bCurrent = parseFloat(b.cumulative_main_net) || 0;
        return bCurrent - aCurrent;
    });
}
```

---

## 排序逻辑说明

### 连续上攻 (consecutive_attacks)

**排序规则**:
1. 按连续上攻次数降序/升序
2. 次数相同时，按涨跌幅降序

**示例**:
```
排序前: [A:3次, B:5次, C:3次, D:1次]
排序后(降序): [B:5次, A:3次(涨5%), C:3次(涨3%), D:1次]
```

### 净额次数 (main_net_count)

**排序规则**:
1. 按净额次数降序/升序
2. 次数相同时，按涨跌幅降序

**示例**:
```
排序前: [A:25次, B:30次, C:25次, D:10次]
排序后(降序): [B:30次, A:25次(涨5%), C:25次(涨3%), D:10次]
```

### 峰值净额 (max_cumulative_main_net)

**排序规则**:
1. 按峰值净额降序/升序
2. null 值排后面
3. 峰值相同时，按当前累计值降序（资金更充裕的在前）

**示例**:
```
排序前: 
  A: 峰值100万, 当前80万
  B: 峰值150万, 当前50万
  C: 峰值100万, 当前120万
  D: null

排序后(降序): 
  [B:150万, C:100万(当前120万), A:100万(当前80万), D:null]
```

---

## 验证清单

### 功能验证

- [ ] 点击"连续上攻"表头，数据按连续上攻次数排序
- [ ] 再次点击，切换升序/降序
- [ ] 点击"净额次数"表头，数据按净额次数排序
- [ ] 再次点击，切换升序/降序
- [ ] 点击"峰值净额"表头，数据按峰值净额排序
- [ ] 再次点击，切换升序/降序
- [ ] 排序后，箭头图标正确显示（▼/▲）

### 兼容性验证

- [ ] 其他列排序不受影响
- [ ] 时间轴切换后排序状态保持
- [ ] 页面刷新后排序状态重置

---

## 相关代码

### 列配置

```javascript
const STOCK_COLUMNS = [
    // ...
    { key: 'consecutive_attacks', label: '连续上攻', sortable: true, default: true },
    { key: 'main_net_count', label: '净额次数', sortable: true, default: true },
    { key: 'max_cumulative_main_net', label: '峰值净额', sortable: true, default: false },
];
```

### 排序状态管理

```javascript
const _rankSort = {
    'stock-ranking': { field: null, dir: 'desc' },
    'bond-ranking':  { field: null, dir: 'desc' }
};
```

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-05-13 | 初始修复 |

---

*修复完成*
