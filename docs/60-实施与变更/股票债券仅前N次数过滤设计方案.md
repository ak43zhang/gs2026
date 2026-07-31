# 股票/债券上攻「仅前N次数」过滤 - 设计方案

## 一、需求

在股票和债券上攻排行的过滤面板中，各新增「仅前N次数」过滤，逻辑与现有「仅前N区间次数」完全一致，排序字段用 `count`（次数）。

N 选项：**全部 / 10 / 20 / 30**（默认"全部"）。

---

## 二、现状（复用成熟模式）

数据已含 `count`（次数）字段：股票 STOCK_COLUMNS 行2232、债券 BOND_COLUMNS 行2375。**纯前端，无后端改动。**

「仅前N次数」与现有「仅前N区间次数」是**同一套机制**：
- 都是 `select` 型过滤器
- 都走管道引擎 `applyToggleableFilter`
- 都纳入类型配置（谓词/排名可切换）
- 都参与持久化

唯一区别：排序字段 `count`（vs `window_count`）、N选项（10/20/30 vs 5/10）。

---

## 三、设计（股票+债券对称，各3处改动）

### 股票侧

**① STOCK_FILTERS 新增配置**（放在"仅前N区间次数"之后）
```javascript
{
    key: 'topn_count',
    label: '仅前N次数',
    type: 'select',
    selectId: 'stock-topn-count-rank',
    options: [
        { value: '0',  label: '全部', default: true },
        { value: '10', label: '10' },
        { value: '20', label: '20' },
        { value: '30', label: '30' },
    ],
    onChange: 'onStockTopNCountChange()',
},
```
> 注：selectId 用 `stock-topn-count-rank`，避免与旧的 `stock-topn-count`（已废弃）混淆。

**② STOCK_PIPELINE 注册项**（排名型，可切换）
```javascript
topn_count: { label: '仅前N次数', kind: 'ranking', fixed: false, sortField: 'count',
              selectId: 'stock-topn-count-rank',
              isActive: () => { const el = document.getElementById('stock-topn-count-rank'); return !!(el && parseInt(el.value) > 0); },
              apply: (d, mode) => applyToggleableFilter(d, mode, 'stock-topn-count-rank', 'count') },
```

**③ 变更处理 + 徽章 + 持久化**
```javascript
function onStockTopNCountChange() { rerenderStockRanking(); saveFilterState(); }
```
- `updateStockFilterBadge`：增加 `stock-topn-count-rank` 值≠0 计入
- `PERSIST_CONTROLS.stock`：增加 `{ id: 'stock-topn-count-rank', type: 'select' }`

### 债券侧（对称）

**① BOND_FILTERS 新增配置**（放在"仅前N区间次数"之后）
```javascript
{
    key: 'topn_count',
    label: '仅前N次数',
    type: 'select',
    selectId: 'bond-topn-count-rank',
    options: [
        { value: '0',  label: '全部', default: true },
        { value: '10', label: '10' },
        { value: '20', label: '20' },
        { value: '30', label: '30' },
    ],
    onChange: 'onBondSelectChange()',
},
```

**② BOND_PIPELINE 注册项**
```javascript
topn_count: { label: '仅前N次数', kind: 'ranking', fixed: false, sortField: 'count',
              selectId: 'bond-topn-count-rank',
              isActive: () => { const el = document.getElementById('bond-topn-count-rank'); return !!(el && parseInt(el.value) > 0); },
              apply: (d, mode) => applyToggleableFilter(d, mode, 'bond-topn-count-rank', 'count') },
```

**③ 徽章 + 持久化**
- `updateBondFilterBadge`：增加 `bond-topn-count-rank` 值≠0 计入
- `PERSIST_CONTROLS.bond`：增加 `{ id: 'bond-topn-count-rank', type: 'select' }`
- 债券 select 的 curVal 默认值处理：`bond-topn-count-rank` 默认 '0'

---

## 四、复用的既有能力（零额外开发）

| 能力 | 说明 |
|------|------|
| 排名/谓词切换 | 自动进入「⚙ 过滤器类型」配置区 |
| 交集模式 | 自动纳入交集前的管道计算 |
| 持久化 | 加入 PERSIST_CONTROLS 即自动存/恢复 |
| 排除0值 | `applyToggleableFilter` 已内置（count>0）|
| 不足N展示 | 已内置（有多少展示多少）|

---

## 五、行为说明

- **排名模式（默认）**：取次数最高的前N只（排除 count=0，不足N则有多少展示多少）
- **谓词模式**：只要 count>0 就保留
- 可与其他排名型（前N金额/前N区间次数/前N行业）**取交集**（顺序无关）

---

## 六、影响范围

| 项 | 评估 |
|----|------|
| 改动文件 | `monitor.html` |
| 改动处 | 股票3处 + 债券3处 = 6处 |
| 后端/数据库 | 无 |
| 现有功能 | 无破坏（纯新增，默认"全部"）|
| 风险 | 低 |

---

## 七、待确认

1. **N选项**：全部 / 10 / 20 / 30 —— 对吗？（区间次数是5/10，次数用10/20/30）
2. **面板顺序**：放在"仅前N区间次数"之后 —— 可以吗？
3. **股票+债券都加** —— 对吗？
4. 默认自动纳入「类型配置」（可切谓词/排名）+ 持久化 + 交集，保持与其他过滤一致 —— 对吗？

审核确认后实施。
