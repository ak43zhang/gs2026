# Dashboard2 数据计算逻辑文档

## 文档信息

- **版本**: v1.0
- **日期**: 2026-05-13
- **模块**: 监控数据计算
- **核心文件**: `src/gs2026/monitor/monitor_stock.py`

---

## 一、概述

本文档详细说明 dashboard2 监控模块中各类数据的计算逻辑，包括：
- 主力净额计算
- 派生字段计算（连续上攻、净额次数、峰值净额）
- 数据流转过程
- 关键算法说明

---

## 二、核心计算流程

### 2.1 整体流程图

```
┌────────────────────────────────────────────────────────────────────┐
│                        实时数据接入                                 │
│                    （每3秒一个数据点）                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 1: 获取当前时段数据 (df_now)                                   │
│  - 从行情接口获取当前股票数据                                        │
│  - 计算单时段 main_net_amount（主力净额）                             │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 2: 获取上一时段数据 (df_prev)                                  │
│  - 从 Redis/MySQL 读取上一时段的累计数据                              │
│  - 包括：cumulative_main_net, consecutive_attacks,                   │
│          main_net_count, max_cumulative_main_net                   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 3: 计算累计和派生字段                                          │
│  - cumulative_main_net = prev.cumulative + current.main_net         │
│  - consecutive_attacks = 连续计数逻辑                                │
│  - main_net_count = prev.count + (current.has_net ? 1 : 0)         │
│  - max_cumulative_main_net = max(prev.max, current.cumulative)      │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Step 4: 存储当前时段数据                                           │
│  - 写入 Redis（实时缓存）                                            │
│  - 写入 MySQL（持久化存储）                                          │
└────────────────────────────────────────────────────────────────────┘
```

---

## 三、主力净额计算

### 3.1 单时段主力净额 (main_net_amount)

**数据来源**: 行情接口

**计算方式**:
```python
# 从行情数据中提取主力净流入金额
main_net_amount = 大单买入金额 - 大单卖出金额
```

**特点**:
- 每3秒计算一次
- 可能为正（净流入）、负（净流出）或零
- 反映该时段主力资金动向

### 3.2 累计主力净额 (cumulative_main_net)

**计算逻辑**（monitor_stock.py）:
```python
def calculate_cumulative_main_net(df_now, df_prev_main):
    """
    计算累计主力净额
    
    Args:
        df_now: 当前时段数据（含 main_net_amount）
        df_prev_main: 上一时段数据（含 cumulative_main_net）
    
    Returns:
        df_now: 添加 cumulative_main_net 字段
    """
    if 'cumulative_main_net' in df_prev_main.columns:
        # 获取上一时段的累计值
        prev_cum = df_prev_main[['stock_code', 'cumulative_main_net']].copy()
        prev_cum['stock_code'] = prev_cum['stock_code'].astype(str).str.strip().str.zfill(6)
        
        # 合并数据
        df_now = df_now.merge(
            prev_cum,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 累计计算：上一时段累计 + 当前时段净额
        df_now['cumulative_main_net_prev'] = df_now['cumulative_main_net_prev'].fillna(0)
        df_now['cumulative_main_net'] = df_now['cumulative_main_net_prev'] + df_now['main_net_amount'].fillna(0)
        df_now = df_now.drop(columns=['cumulative_main_net_prev'], errors='ignore')
    else:
        # 首次：直接取当前净额
        df_now['cumulative_main_net'] = df_now['main_net_amount'].fillna(0)
    
    return df_now
```

**示例**:
```
时段    main_net_amount    cumulative_main_net
09:30   +10万             +10万
09:33   +5万              +15万
09:36   -3万              +12万
09:39   +8万              +20万
```

---

## 四、派生字段计算

### 4.1 consecutive_attacks（连续上攻次数）

**定义**: 股票连续出现主力净流入的时段数量

**算法逻辑**:
```python
def calculate_consecutive_attacks(df_now, df_prev_main):
    """
    计算连续上攻次数
    
    逻辑：
    - 如果当前时段有主力净额（|main_net| > 0），连续次数 +1
    - 如果当前时段无主力净额，连续次数重置为 0
    """
    # 判断当前时段是否有主力净额
    has_main_net = (df_now['main_net_amount'].abs() > 1e-6).astype(int)
    
    if 'consecutive_attacks' in df_prev_main.columns:
        # 获取上一时段的连续次数
        prev_attacks = df_prev_main[['stock_code', 'consecutive_attacks']].copy()
        prev_attacks['stock_code'] = prev_attacks['stock_code'].astype(str).str.strip().str.zfill(6)
        
        df_now = df_now.merge(
            prev_attacks,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 核心逻辑：
        # 连续次数 = (上一时段连续次数 × 当前是否有净额) + 当前是否有净额
        # 解释：
        # - 如果当前有净额：连续次数 = 上一时段次数 + 1
        # - 如果当前无净额：连续次数 = 0
        df_now['consecutive_attacks_prev'] = df_now['consecutive_attacks_prev'].fillna(0)
        df_now['consecutive_attacks'] = df_now['consecutive_attacks_prev'] * has_main_net + has_main_net
        df_now = df_now.drop(columns=['consecutive_attacks_prev'], errors='ignore')
    else:
        # 首次：当前有净额则为1，否则为0
        df_now['consecutive_attacks'] = has_main_net
    
    return df_now
```

**计算示例**:
```
时段    main_net_amount    has_main_net    consecutive_attacks
09:30   +10万             1               1  (首次)
09:33   +5万              1               2  (连续)
09:36   0                 0               0  (中断)
09:39   +8万              1               1  (重新计数)
09:42   -2万              1               2  (连续，负值也算有净额)
09:45   0                 0               0  (中断)
```

### 4.2 main_net_count（净额次数）

**定义**: 当日累计出现主力净额的次数

**与 count（上攻次数）的区别**:
- `count`: 上攻次数（价格异动触发）
- `main_net_count`: 有主力净额出现的次数（资金异动）

**算法逻辑**:
```python
def calculate_main_net_count(df_now, df_prev_main):
    """
    计算净额次数
    
    逻辑：
    - 累计计数：只要当前时段有主力净额，次数 +1
    - 与连续次数不同，这是累计值，不会重置
    """
    # 判断当前时段是否有主力净额
    has_main_net = (df_now['main_net_amount'].abs() > 1e-6).astype(int)
    
    if 'main_net_count' in df_prev_main.columns:
        # 获取上一时段的次数
        prev_count = df_prev_main[['stock_code', 'main_net_count']].copy()
        prev_count['stock_code'] = prev_count['stock_code'].astype(str).str.strip().str.zfill(6)
        
        df_now = df_now.merge(
            prev_count,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 累计：上一时段次数 + 当前时段是否有净额
        df_now['main_net_count_prev'] = df_now['main_net_count_prev'].fillna(0)
        df_now['main_net_count'] = df_now['main_net_count_prev'] + has_main_net
        df_now = df_now.drop(columns=['main_net_count_prev'], errors='ignore')
    else:
        # 首次：当前有净额则为1，否则为0
        df_now['main_net_count'] = has_main_net
    
    return df_now
```

**计算示例**:
```
时段    main_net_amount    has_main_net    main_net_count
09:30   +10万             1               1
09:33   +5万              1               2
09:36   0                 0               2  (不增加)
09:39   +8万              1               3
09:42   -2万              1               4
09:45   0                 0               4  (不增加)
```

### 4.3 max_cumulative_main_net（峰值净额）

**定义**: 当日累计主力净额的最大值（历史峰值）

**关键特性**:
- 只增不减（历史最高值）
- 用于衡量当前资金相对于峰值的回落程度

**算法逻辑**:
```python
def calculate_max_cumulative_main_net(df_now, df_prev_main):
    """
    计算峰值净额
    
    逻辑：
    - 历史峰值 vs 当前累计值，取大者
    - 如果当前累计值 > 历史峰值，更新峰值
    """
    if 'max_cumulative_main_net' in df_prev_main.columns:
        # 获取上一时段的峰值
        prev_max = df_prev_main[['stock_code', 'max_cumulative_main_net']].copy()
        prev_max['stock_code'] = prev_max['stock_code'].astype(str).str.strip().str.zfill(6)
        
        df_now = df_now.merge(
            prev_max,
            on='stock_code',
            how='left',
            suffixes=('', '_prev')
        )
        
        # 取大者：max(历史峰值, 当前累计值)
        df_now['max_cumulative_main_net_prev'] = df_now['max_cumulative_main_net_prev'].fillna(0)
        df_now['max_cumulative_main_net'] = df_now[['max_cumulative_main_net_prev', 'cumulative_main_net']].max(axis=1)
        df_now = df_now.drop(columns=['max_cumulative_main_net_prev'], errors='ignore')
    else:
        # 首次：直接取当前累计值
        df_now['max_cumulative_main_net'] = df_now['cumulative_main_net']
    
    return df_now
```

**计算示例**:
```
时段    main_net_amount    cumulative_main_net    max_cumulative_main_net
09:30   +10万             +10万                 +10万  (首次)
09:33   +5万              +15万                 +15万  (更新峰值)
09:36   -3万              +12万                 +15万  (保持峰值)
09:39   +8万              +20万                 +20万  (更新峰值)
09:42   -25万             -5万                  +20万  (保持峰值，资金大幅流出)
09:45   +2万              -3万                  +20万  (保持峰值)
```

---

## 五、前端回落百分比计算

### 5.1 计算公式

```javascript
// 回落百分比 = (峰值 - 当前) / 峰值 × 100%
const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
```

### 5.2 状态判断

```javascript
// 回落超过20%（当前 < 峰值 × 0.8）
const isDropping = current < peak * 0.8;

// 保持在峰值95%以上（当前 ≥ 峰值 × 0.95）
const isStrong = current >= peak * 0.95;
```

### 5.3 显示规则

| 状态 | 条件 | 样式 | 指示器 |
|------|------|------|--------|
| 强势 | current ≥ peak × 0.95 | peak-strong（绿色） | → |
| 正常 | peak × 0.8 ≤ current < peak × 0.95 | 默认 | 无 |
| 回落 | current < peak × 0.8 | peak-warning（红色） | ↓ |

---

## 六、完整计算示例

### 6.1 场景：股票 301396 某日交易

```
时段    main_net    cumulative    max_cum    attacks    count    说明
09:30   +50万       +50万         +50万      1          1        开盘净流入
09:33   +30万       +80万         +80万      2          2        继续流入
09:36   +20万       +100万        +100万     3          3        达到峰值
09:39   -10万       +90万         +100万     4          4        小幅流出
09:42   -30万       +60万         +100万     5          5        继续流出
09:45   -50万       +10万         +100万     6          6        大幅流出
09:48   -20万       -10万         +100万     0          7        中断连续
09:51   +5万        -5万          +100万     1          8        重新流入
09:54   +10万       +5万          +100万     2          9        继续流入
09:57   +15万       +20万         +100万     3          10       继续流入
10:00   +20万       +40万         +100万     4          11       继续流入
...
15:00   -10万       -248.1万      +66.1万    0          25       收盘
```

### 6.2 收盘时数据

```json
{
  "code": "301396",
  "main_net_amount": -2481000,      // 当前累计值（显示为"主力资金"）
  "max_cumulative_main_net": 661000, // 峰值净额
  "consecutive_attacks": 0,          // 当前无连续上攻
  "main_net_count": 25               // 当日有25个时段有净额
}
```

### 6.3 前端显示

```
主力资金: -248.1万
峰值净额: 66.1万 ↓
回落: 100%  // (66.1 - (-248.1)) / 66.1 * 100 = 475%？
```

**注意**: 这里出现了 Bug！
- 实际 `current` 应该为 `-248.1万`
- 但由于字段名不匹配，`current` 被错误地取为 `0`
- 导致计算结果错误

---

## 七、Bug 详细分析

### 7.1 问题描述

**现象**: 峰值净额列显示 100% 回落

**根本原因**: 后端和前端的字段名不匹配

### 7.2 后端代码（monitor.py）

```python
# 第 417-418 行
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
# ❌ 缺少 stock['cumulative_main_net'] 的赋值
```

后端只赋值了 `main_net_amount`，没有赋值 `cumulative_main_net`。

### 7.3 前端代码（monitor.html）

```javascript
// 第 1350 行
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;  // ❌ 实际为 undefined
    const peak = item.max_cumulative_main_net || 0;  // ✓ 66.1万
    
    // 计算回落百分比
    const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
    // 结果: (661000 - 0) / 661000 * 100 = 100%
}
```

### 7.4 修复方案

**方案一：后端添加字段**（推荐）

```python
# monitor.py 第 417-418 行后添加
stock['cumulative_main_net'] = main_net if main_net is not None else 0
```

**方案二：前端修改字段名**

```javascript
// monitor.html 第 1350 行
const current = item.main_net_amount || 0;  // 改为使用 main_net_amount
```

---

## 八、数据验证检查点

### 8.1 合理性检查

| 检查项 | 规则 | 错误示例 |
|--------|------|----------|
| cumulative_main_net | 应该等于当日所有 main_net_amount 之和 | 数据不一致 |
| max_cumulative_main_net | 应该 ≥ cumulative_main_net | 峰值小于当前值 |
| max_cumulative_main_net | 应该 ≥ 0（如果是净流入峰值） | 负值峰值 |
| consecutive_attacks | 应该 ≤ main_net_count | 连续次数大于总次数 |
| main_net_count | 应该 ≥ consecutive_attacks | 总次数小于连续次数 |

### 8.2 调试日志

在 monitor_stock.py 中添加了调试日志：
```python
non_zero_main = (df_now['main_net_amount'].abs() > 1e-6).sum()
non_zero_cum = (df_now['cumulative_main_net'] != 0).sum()
non_zero_count = (df_now['main_net_count'] > 0).sum()
logger.info(f"主力净额计算完成: main={non_zero_main}, cum={non_zero_cum}, count={non_zero_count}")
```

---

## 九、性能优化

### 9.1 批量查询优化

```python
# 优化前：逐个查询（N次查询）
for code in stock_codes:
    data = query_one(code)  # N次查询

# 优化后：批量查询（1次查询）
codes_str = ','.join([f"'{c}'" for c in stock_codes])
data = query_batch(codes_str)  # 1次查询
```

### 9.2 Redis 缓存优化

- 使用 `timestamps` list 存储时间点
- 使用 DataFrame 批量存储/读取
- 压缩存储节省内存

---

## 十、附录

### 10.1 代码文件清单

| 文件 | 功能 | 关键函数 |
|------|------|----------|
| `monitor_stock.py` | 数据计算 | `calculate_cumulative_main_net`, `calculate_consecutive_attacks`, `calculate_main_net_count`, `calculate_max_cumulative_main_net` |
| `monitor.py` | 数据接口 | `_enrich_change_pct_and_main_net`, `_get_change_pct_and_main_net_batch` |
| `monitor.html` | 前端展示 | 峰值净额列渲染逻辑 |

### 10.2 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-05-13 | 初始版本 |

---

*文档结束*
