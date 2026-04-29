# 股票上攻排行主力净额排序方案

## 当前排序逻辑

### 后端排序 (monitor.py)
```python
# 排序：红名单优先，然后按次数倒序
data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))
```

### 前端排序 (monitor.html)
支持字段：
- `change_pct` - 涨跌幅
- `count` - 次数（默认）
- `industry` - 行业
- `bond_code` - 债券代码

当前涨跌幅排序逻辑：
```javascript
if (st.field === 'change_pct') {
    sorted.sort((a, b) => {
        const aVal = (a.change_pct !== null && a.change_pct !== undefined) ? parseFloat(a.change_pct) : null;
        const bVal = (b.change_pct !== null && b.change_pct !== undefined) ? parseFloat(b.change_pct) : null;
        if (aVal === null && bVal === null) return 0;
        if (aVal === null) return 1;
        if (bVal === null) return -1;
        return (aVal - bVal) * dir;
    });
}
```

---

## 方案：增加主力净额排序

### 1. 前端修改 (monitor.html)

#### 1.1 增加表头排序按钮
```javascript
// 在表头部分增加主力净额排序
if (isStockRanking) {
    const mnCls = sortSt.field === 'main_net_amount' ? ' sort-active' : '';
    h += `<th class="sortable-th${mnCls}" onclick="toggleRankSort('${id}','main_net_amount')">主力净额${getRankSortArrow(id,'main_net_amount')}</th>`;
}
```

#### 1.2 增加排序逻辑
```javascript
else if (st.field === 'main_net_amount') {
    sorted.sort((a, b) => {
        const aVal = (a.main_net_amount !== null && a.main_net_amount !== undefined) ? parseFloat(a.main_net_amount) : null;
        const bVal = (b.main_net_amount !== null && b.main_net_amount !== undefined) ? parseFloat(b.main_net_amount) : null;
        if (aVal === null && bVal === null) return 0;
        if (aVal === null) return 1;  // null值排后面
        if (bVal === null) return -1;
        return (aVal - bVal) * dir;  // 主力净额降序/升序
    });
}
```

#### 1.3 默认排序规则（与涨跌幅一致）
- 降序（desc）：净流入大的在前（红色）
- 升序（asc）：净流出大的在前（绿色）
- null/0值排在最后

### 2. 排序规则对比

| 字段 | 降序(desc) | 升序(asc) | null值处理 |
|------|-----------|-----------|-----------|
| change_pct | 涨幅大的在前 | 跌幅大的在前 | 排最后 |
| main_net_amount | 净流入大的在前 | 净流出大的在前 | 排最后 |

### 3. 显示优化

主力净额显示格式：
```javascript
// 格式化显示（万为单位，保留1位小数）
function formatMainNet(value) {
    if (value === null || value === undefined || value === 0) return '-';
    const wan = value / 10000;
    return wan.toFixed(1) + '万';
}

// 颜色：净流入红色，净流出绿色
function getMainNetColor(value) {
    if (value > 0) return '#e53935';  // 红色-流入
    if (value < 0) return '#43a047';  // 绿色-流出
    return '#999';  // 灰色-无数据
}
```

---

## 实施步骤

### 步骤1：前端修改 monitor.html
1. 在表头增加主力净额排序按钮
2. 在sortRankData函数中增加main_net_amount排序逻辑
3. 保持与涨跌幅排序规则一致

### 步骤2：验证
1. 点击主力净额表头，验证排序功能
2. 验证降序：净流入大的在前
3. 验证升序：净流出大的在前
4. 验证null值排最后

---

## 审核要点

1. **是否接受此方案？**
2. **主力净额排序规则是否与涨跌幅一致？**
   - 降序：净流入大的在前（红色）
   - 升序：净流出大的在前（绿色）
3. **是否需要其他排序规则？**
   - 如：主力净额绝对值排序
   - 如：主力净额+涨跌幅组合排序
4. **是否立即实施？**
