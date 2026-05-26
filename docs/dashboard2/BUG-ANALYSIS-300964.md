# Bug 深度分析：300964 峰值净额显示异常

## 问题现象

**股票**: 300964
**时间**: 11:25:18
**数据**:
- 主力净额: -60.4万
- 峰值净额: -（显示为横线）

---

## 根因分析

### 核心问题：峰值净额的计算逻辑

**代码位置**: `src/gs2026/monitor/monitor_stock.py` 第 732 行

```python
df_now['max_cumulative_main_net'] = df_now[['max_cumulative_main_net_prev', 'cumulative_main_net']].max(axis=1)
```

**问题**: 使用 `.max(axis=1)` 在负数场景下的行为

### 场景推演

**当日资金流向（假设）**:
```
时间      main_net    cumulative    max_cumulative    说明
09:30     -10万       -10万         -10万            首次，直接取
09:33     -20万       -30万         -10万            max(-10, -30) = -10
09:36     -15万       -45万         -10万            max(-10, -45) = -10
...
11:25     -15.4万     -60.4万       -10万            max(-10, -60.4) = -10
```

**结果**:
- 当日资金持续净流出
- 累计值一直是负数
- 峰值净额 = 最大的负数 = -10万（最接近0的）

### 前端显示问题

**前端代码** (`monitor.html` 第 1380-1382 行):
```javascript
const peak = item.max_cumulative_main_net || 0;
if (peak === 0) return '<td>-</td>';
```

**问题**:
1. 后端返回 `-100000`（-10万）
2. 前端使用 `|| 0`，对于负数 `-100000 || 0 = -100000`（没问题）
3. 但后端 `_extract_derived` 使用 `int(val)`，可能有问题

**后端代码** (`monitor.py` 第 460 行):
```python
derived_maps[fname][code] = int(val) if pd.notna(val) else 0
```

**问题**: 
- `int(-100000.50)` = `-100000`（截断小数）
- 但负数本身没问题

### 真正的问题

让我重新检查前端代码：

```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;  // -60.4万
    const peak = item.max_cumulative_main_net || 0;  // -10万
    
    if (peak === 0) return '<td>-</td>';  // peak = -10万，不成立
    
    // 计算回落百分比
    const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
    // peak = -10万 < 0，所以 dropPct = 0
```

**发现问题**:
```javascript
const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
```

当 `peak < 0` 时，直接返回 `0`，没有计算！

**后续逻辑**:
```javascript
const isDropping = current < peak * 0.8;  // -60.4 < -10*0.8 = -8，成立
const isStrong = current >= peak * 0.95;  // -60.4 >= -9.5，不成立

if (isDropping) {
    colorClass = 'peak-warning';
    indicator = '↓';
}
```

**formatMoney 问题**:
```javascript
function formatMoney(value) {
    if (!value || value === 0) return '-';  // ← 问题：-10万被认为是 falsy？
```

**验证**:
```javascript
!(-100000) = false  // 负数不是 falsy
(-100000 || 0) = -100000  // 没问题
```

所以 `formatMoney(-100000)` 应该返回 `'-10.0万'`，不是 `'-'`。

### 数据流追踪

让我追踪数据从数据库到前端的流程：

**1. 数据库** (`monitor_gp_sssj_20260513`):
```sql
SELECT * FROM monitor_gp_sssj_20260513 
WHERE stock_code = '300964' AND time = '11:25:18'

结果：
- cumulative_main_net: -604000.00
- max_cumulative_main_net: -100000.00  （或 NULL？）
```

**2. 后端查询** (`monitor.py` 第 518-530 行):
```python
query = f"""
    SELECT stock_code, change_pct, cumulative_main_net, {derived_cols}
    FROM {table_name}
    WHERE time = '{time_str}' AND stock_code IN ({codes_str})
"""
```

**3. 派生字段提取** (`monitor.py` 第 457-460 行):
```python
derived_maps[fname][code] = int(val) if pd.notna(val) else 0
```

**问题**: 如果 `max_cumulative_main_net = -100000.50`，`int()` 后变成 `-100000`。

**4. 数据填充** (`monitor.py` 第 417-422 行):
```python
for fname, fmap in derived_maps.items():
    stock[fname] = fmap.get(code, 0)  # 如果缺失，默认值为 0
```

**问题**: 如果 `max_cumulative_main_net` 不在 `derived_maps` 中，会被设为 `0`！

### 根本原因

**问题1**: `_extract_derived` 函数中，如果 `max_cumulative_main_net` 列存在但某行值为 `NULL` 或 `NaN`，会被设为 `0`。

**问题2**: 如果 `max_cumulative_main_net` 列不存在（旧数据），`derived_maps` 中不会有该字段，前端会读到 `undefined`。

**问题3**: 前端 `peak === 0` 的判断，把 `0` 和缺失混为一谈。

---

## 修复方案

### 修复1：区分"0值"和"缺失值"

**文件**: `src/gs2026/dashboard2/routes/monitor.py`

**修改** `_extract_derived` 函数:
```python
def _extract_derived(df, code_col):
    """从DataFrame中提取所有派生字段"""
    for fname in DERIVED_DISPLAY_FIELDS:
        if fname in df.columns:
            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                val = row.get(fname)
                # 只存储有效值，缺失值不存储（保持为 None）
                if pd.notna(val):
                    derived_maps[fname][code] = float(val)  # 保持浮点精度
```

**修改** 数据填充逻辑:
```python
# 派生字段（自动填充，缺失值保持为 null）
for fname, fmap in derived_maps.items():
    stock[fname] = fmap.get(code)  # 不设置默认值，保持 undefined/null
```

### 修复2：前端正确处理负数和缺失

**文件**: `src/gs2026/dashboard2/templates/monitor.html`

**修改** 峰值净额显示逻辑:
```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;
    
    // 检查数据是否存在
    if (item.max_cumulative_main_net === undefined || item.max_cumulative_main_net === null) {
        return '<td>-</td>';  // 数据缺失
    }
    
    const peak = parseFloat(item.max_cumulative_main_net);
    
    // 峰值净额显示（即使是负数也显示）
    const peakStr = formatMoney(peak);
    
    // 回落百分比计算（处理正负数）
    let dropPct = 0;
    let colorClass = '';
    let indicator = '';
    
    if (peak !== 0) {
        // 统一公式：(峰值 - 当前) / |峰值| × 100%
        // 当 peak < 0 且 current < peak 时，表示资金继续流出
        dropPct = ((peak - current) / Math.abs(peak) * 100).toFixed(1);
        
        // 判断逻辑：当前值相对于峰值的变化
        if (peak > 0) {
            // 正峰值场景
            const isDropping = current < peak * 0.8;
            const isStrong = current >= peak * 0.95;
            
            if (isDropping) {
                colorClass = 'peak-warning';
                indicator = '↓';
            } else if (isStrong) {
                colorClass = 'peak-strong';
                indicator = '→';
            }
        } else {
            // 负峰值场景（当日一直净流出）
            // current = -60.4万, peak = -10万
            // 资金从 -10万 恶化到 -60.4万
            const isWorsening = current < peak * 1.2;  // 恶化超过20%
            const isImproving = current >= peak * 0.95;  // 改善（接近0）
            
            if (isWorsening) {
                colorClass = 'peak-warning';  // 红色：资金持续恶化
                indicator = '↓↓';
            } else if (isImproving) {
                colorClass = 'peak-strong';  // 绿色：资金在回流
                indicator = '↑';
            }
        }
    }
    
    return `<td class="${colorClass}">
        <div class="peak-value">${peakStr} ${indicator}</div>
        ${peak !== 0 ? `<div class="drop-pct small">${dropPct}%</div>` : ''}
    </td>`;
}
```

### 修复3：formatMoney 函数

**确保负数正确处理**:
```javascript
function formatMoney(value) {
    if (value === null || value === undefined) return '-';
    const num = parseFloat(value);
    if (num === 0) return '0';
    
    const sign = num < 0 ? '-' : '';
    const absNum = Math.abs(num);
    
    if (absNum >= 100000000) {
        return sign + (absNum / 100000000).toFixed(2) + '亿';
    } else if (absNum >= 10000) {
        return sign + (absNum / 10000).toFixed(1) + '万';
    } else {
        return sign + absNum.toFixed(0);
    }
}
```

---

## 验证方案

### 测试用例1：300964 场景

**输入数据**:
```json
{
  "code": "300964",
  "cumulative_main_net": -604000,
  "max_cumulative_main_net": -100000
}
```

**预期显示**:
- 主力净额: -60.4万
- 峰值净额: -10万 ↓↓
- 回落百分比: -504.0%（或显示为"恶化504%"）

**计算**:
```
peak = -10万, current = -60.4万
dropPct = (-10 - (-60.4)) / |-10| × 100 = 50.4 / 10 × 100 = 504%

判断：
current < peak × 1.2 = -10 × 1.2 = -12
-60.4 < -12，成立，显示红色警告
```

### 测试用例2：正常正峰值

**输入数据**:
```json
{
  "code": "301396",
  "cumulative_main_net": -2481000,
  "max_cumulative_main_net": 661000
}
```

**预期显示**:
- 主力净额: -248.1万
- 峰值净额: 66.1万 ↓
- 回落百分比: 475.2%

### 测试用例3：数据缺失

**输入数据**:
```json
{
  "code": "300001",
  "cumulative_main_net": 100000
  // max_cumulative_main_net 缺失
}
```

**预期显示**:
- 主力净额: +10万
- 峰值净额: -

---

## 总结

| 问题 | 根因 | 修复方案 |
|------|------|----------|
| 峰值净额显示"-" | 1. 后端将缺失值设为0<br>2. 前端将0视为缺失 | 1. 后端不存储缺失值<br>2. 前端区分undefined和0 |
| 负数峰值计算错误 | 前端只处理正峰值 | 添加负峰值处理逻辑 |
| 精度丢失 | 后端使用int() | 使用float() |

---

*分析报告完成*
