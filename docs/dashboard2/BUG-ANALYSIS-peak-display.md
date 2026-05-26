# Bug 分析报告：峰值净额显示异常

## 问题描述

以股票 **300964** 为例，11:25:18 时：
- **主力净额**: -60.4万（有值）
- **峰值净额**: -（显示为横线，不符合逻辑）

**预期**: 峰值净额应该显示为数值（可能是0或其他值）
**实际**: 峰值净额显示为 "-"

---

## 问题1：峰值净额显示为"-"

### 根因分析

**前端显示逻辑** (`monitor.html` 第 1380-1382 行):
```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;
    const peak = item.max_cumulative_main_net || 0;
    
    if (peak === 0) return '<td>-</td>';  // ← 问题：peak为0时显示"-"
```

**问题**: 
- 当 `max_cumulative_main_net = 0` 时，直接返回 "-"
- 但 `max_cumulative_main_net = 0` 是一个有效值（表示当日无净流入峰值）
- 这与 "数据缺失" 的 "-" 混淆了

**后端数据逻辑** (`monitor.py` 第 457-460 行):
```python
def _extract_derived(df, code_col):
    for fname in DERIVED_DISPLAY_FIELDS:
        if fname in df.columns:
            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                val = row.get(fname)
                derived_maps[fname][code] = int(val) if pd.notna(val) else 0
```

**问题**:
1. `max_cumulative_main_net` 被强制转为 `int`，丢失小数精度
2. 当 `val = 0` 时，存储为 `0`
3. 当 `val = null/NaN` 时，也存储为 `0`

### 场景分析

**场景A：当日无主力净流入**
```
时间线：
09:30: main_net = -10万, cumulative = -10万, max_cumulative = -10万
09:33: main_net = -20万, cumulative = -30万, max_cumulative = -10万（峰值）
...
11:25: main_net = -30万, cumulative = -60.4万, max_cumulative = -10万（峰值）

结果：
- 主力净额：-60.4万（当前累计）
- 峰值净额：-10万（当日最高值，可能是负数）
```

**场景B：数据缺失**
```
- max_cumulative_main_net 字段不存在
- 或值为 null/NaN
- 应该显示 "-"
```

### 修复方案

**方案1：区分"0值"和"缺失"**（推荐）

修改前端逻辑，使用 `null` 表示缺失，使用 `0` 表示实际值为0：

```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;
    const peak = item.max_cumulative_main_net;
    
    // 区分"缺失"和"0值"
    if (peak === null || peak === undefined) {
        return '<td>-</td>';  // 数据缺失
    }
    
    const peakNum = parseFloat(peak) || 0;
    
    // 峰值净额显示逻辑（即使是0也显示）
    const peakStr = formatMoney(peakNum);
    
    // 回落百分比计算
    let dropPct = 0;
    let colorClass = '';
    let indicator = '';
    
    if (peakNum !== 0) {
        dropPct = ((peakNum - current) / peakNum * 100).toFixed(1);
        const isDropping = current < peakNum * 0.8;
        const isStrong = current >= peakNum * 0.95;
        
        if (isDropping) {
            colorClass = 'peak-warning';
            indicator = '↓';
        } else if (isStrong) {
            colorClass = 'peak-strong';
            indicator = '→';
        }
    }
    
    return `<td class="${colorClass}">
        <div class="peak-value">${peakStr} ${indicator}</div>
        ${peakNum !== 0 ? `<div class="drop-pct small">${dropPct}%</div>` : ''}
    </td>`;
}
```

**方案2：后端使用 null 表示缺失**

修改 `_extract_derived` 函数：
```python
def _extract_derived(df, code_col):
    for fname in DERIVED_DISPLAY_FIELDS:
        if fname in df.columns:
            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                val = row.get(fname)
                # 使用 null 表示缺失，不转换为0
                if pd.notna(val):
                    derived_maps[fname][code] = float(val)  # 保持浮点数精度
                # 缺失值不放入字典，前端会读到 undefined
```

---

## 问题2：主力净额被初始化为"-"

### 排查分析

**可能原因1：后端返回 null**
```python
# monitor.py 第 417-419 行
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
stock['cumulative_main_net'] = main_net if main_net is not None else 0
```

当 `main_net = None` 时，赋值为 `0`，不是 `"-"`。

**可能原因2：前端显示逻辑**
```javascript
// monitor.html 第 1320-1324 行
case 'main_net_amount': {
    const v = item.main_net_amount || 0;
    const cls = v > 0 ? 'main-net-up' : (v < 0 ? 'main-net-down' : 'main-net-neutral');
    const txt = v !== 0 ? (v > 0 ? '+' : '') + (v / 10000).toFixed(1) + '万' : '-';  // ← 0显示为"-"
    return `<td class="${cls}">${txt}</td>`;
}
```

**问题**: 当 `v = 0` 时，显示为 `"-"`，这可能不是 bug，而是设计如此。

**可能原因3：数据获取失败**

如果 `_get_change_pct_and_main_net_batch` 返回失败：
```python
# monitor.py 第 430-434 行（异常处理）
except Exception as e:
    print(f"添加涨跌幅和主力净额失败: {e}")
    for stock in stocks:
        stock['change_pct'] = '-'
        stock['main_net_amount'] = 0  # 赋值为0，不是"-"
        stock['cumulative_main_net'] = 0
    return stocks
```

异常处理时赋值为 `0`，不是 `"-"`。

### 结论

**"主力净额被初始化为'-'" 可能不是 bug**，而是：
1. 实际值为 `0` 时，前端显示为 `"-"`（设计如此）
2. 或者用户观察到的现象有其他原因

**需要进一步确认**:
- 用户说的 "-" 是指 `"-"` 字符串，还是指数据缺失？
- 具体是哪个股票、哪个时间点出现这个问题？

---

## 修复建议

### 修复1：峰值净额显示逻辑（前端）

**文件**: `src/gs2026/dashboard2/templates/monitor.html`

**位置**: 第 1380-1410 行

**修改内容**:
```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;
    const peak = item.max_cumulative_main_net;
    
    // 数据缺失时显示"-"
    if (peak === null || peak === undefined) {
        return '<td>-</td>';
    }
    
    const peakNum = parseFloat(peak) || 0;
    
    // 峰值为0时，简化显示
    if (peakNum === 0) {
        return '<td>0</td>';
    }
    
    // 计算回落百分比
    const dropPct = ((peakNum - current) / peakNum * 100).toFixed(1);
    const isDropping = current < peakNum * 0.8;
    const isStrong = current >= peakNum * 0.95;
    
    let colorClass = '';
    let indicator = '';
    
    if (isDropping) {
        colorClass = 'peak-warning';
        indicator = '↓';
    } else if (isStrong) {
        colorClass = 'peak-strong';
        indicator = '→';
    }
    
    const peakStr = formatMoney(peakNum);
    
    return `<td class="${colorClass}">
        <div class="peak-value">${peakStr} ${indicator}</div>
        <div class="drop-pct small">${dropPct}%</div>
    </td>`;
}
```

### 修复2：派生字段精度（后端）

**文件**: `src/gs2026/dashboard2/routes/monitor.py`

**位置**: 第 457-460 行

**修改内容**:
```python
def _extract_derived(df, code_col):
    """从DataFrame中提取所有派生字段"""
    for fname in DERIVED_DISPLAY_FIELDS:
        if fname in df.columns:
            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                val = row.get(fname)
                # 保持浮点数精度，不使用 int()
                if pd.notna(val):
                    derived_maps[fname][code] = float(val)
                # 缺失值不放入字典
```

---

## 验证方案

### 测试用例1：峰值净额为0

**数据**:
```json
{
  "code": "300964",
  "main_net_amount": -604000,
  "cumulative_main_net": -604000,
  "max_cumulative_main_net": 0
}
```

**预期显示**:
- 主力净额: -60.4万
- 峰值净额: 0（或简化显示）

### 测试用例2：峰值净额为负

**数据**:
```json
{
  "code": "300964",
  "main_net_amount": -604000,
  "cumulative_main_net": -604000,
  "max_cumulative_main_net": -100000
}
```

**预期显示**:
- 主力净额: -60.4万
- 峰值净额: -10万
- 回落百分比: 计算正确

### 测试用例3：数据缺失

**数据**:
```json
{
  "code": "300964",
  "main_net_amount": -604000,
  "cumulative_main_net": -604000
  // max_cumulative_main_net 缺失
}
```

**预期显示**:
- 主力净额: -60.4万
- 峰值净额: -

---

## 总结

| 问题 | 根因 | 修复方案 |
|------|------|----------|
| 峰值净额显示"-" | 前端将 peak=0 视为缺失 | 区分 null 和 0 |
| 主力净额显示"-" | 可能是设计如此（0显示为-） | 需确认是否为问题 |
| 精度丢失 | 后端使用 int() 转换 | 使用 float() 保持精度 |

---

*分析报告完成*
