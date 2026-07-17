# 龙头股识别优化方案v2 - AI保留+简化版补全+Role细分

## 核心需求

1. **保留AI定义的龙头**：如果AI已判定为龙头，保持不动
2. **无龙头主线用简化版补全**：如果AI未定义龙头，按时间规则补龙头
3. **Role细分扩展**：将"龙头"细分为三类（基于体量）

---

## 一、Role细分设计

### 新Role体系（5类）

| Role | 定义 | 识别标准 | 策略 |
|------|------|---------|------|
| **权重龙头** | 指数大盘型 | 流通市值>500亿 + 龙头地位 | 趋势跟随，不追高 |
| **板块中军** | 容量中坚型 | 200亿≤流通市值≤500亿 + 龙头地位 | 可打板可低吸 |
| **小盘情绪龙** | 短线连板型 | 流通市值<200亿 + 龙头地位 | 打板为主，快进快出 |
| **补涨** | 跟风补涨型 | 涨停时间2-3名 | 谨慎参与 |
| **跟风** | 被动上涨型 | 涨停时间4名以后 | 不参与 |

### 细分逻辑

```
主线内所有股票
    ↓
AI是否已定义龙头？
    ↓ 是
保留AI定义的龙头类型（权重龙头/板块中军/小盘情绪龙）
    ↓ 否
按时间排序，第1只 → 小盘情绪龙/板块中军/权重龙头（看市值）
第2-3只 → 补涨
第4只以后 → 跟风
```

---

## 二、实施逻辑

### Step 1: 检查AI是否已定义龙头

```python
# 查询该主线是否已有role='龙头'的股票
has_ai_leader = check_if_ai_defined_leader(mainline_id)

if has_ai_leader:
    # 保留AI定义的龙头，只对其他股票重新计算
    keep_ai_leader_and_recalc_others()
else:
    # 按简化版规则补龙头
    apply_simplified_rule()
```

### Step 2: 简化版规则（无AI龙头时）

```python
def apply_simplified_rule(stocks):
    """
    按时间排序，根据市值细分龙头类型
    """
    sorted_stocks = sorted(stocks, key=lambda x: x['anomaly_time'])
    
    # 第1只：根据市值细分龙头类型
    first_stock = sorted_stocks[0]
    market_cap = first_stock['circulating_market_cap']  # 流通市值（亿）
    
    if market_cap > 500:
        first_stock['new_role'] = '权重龙头'
        first_stock['score'] = 100
    elif 200 <= market_cap <= 500:
        first_stock['new_role'] = '板块中军'
        first_stock['score'] = 100
    else:
        first_stock['new_role'] = '小盘情绪龙'
        first_stock['score'] = 100
    
    # 第2-3只：补涨
    for i in [1, 2]:
        if i < len(sorted_stocks):
            sorted_stocks[i]['new_role'] = '补涨'
            sorted_stocks[i]['score'] = max(85 - i * 15, 20)
    
    # 第4只及以后：跟风
    for i in range(3, len(sorted_stocks)):
        sorted_stocks[i]['new_role'] = '跟风'
        sorted_stocks[i]['score'] = max(55 - (i - 3) * 5, 20)
    
    return sorted_stocks
```

### Step 3: 保留AI龙头时的处理

```python
def keep_ai_leader_and_recalc_others(engine, mainline_id, stocks):
    """
    保留AI定义的龙头，对其他股票重新计算role
    """
    # 找出AI定义的龙头
    ai_leader = [s for s in stocks if s['role'] in ['权重龙头', '板块中军', '小盘情绪龙', '龙头']]
    
    # 对其他股票按时间排序
    other_stocks = [s for s in stocks if s not in ai_leader]
    other_stocks.sort(key=lambda x: x['anomaly_time'])
    
    # 对其他股票重新分配role（不再有龙头，只有补涨和跟风）
    for i, stock in enumerate(other_stocks):
        if i < 2:  # 第1-2只其他股票 → 补涨
            stock['new_role'] = '补涨'
            stock['score'] = max(70 - i * 15, 20)
        else:  # 第3只及以后 → 跟风
            stock['new_role'] = '跟风'
            stock['score'] = max(40 - (i - 2) * 5, 20)
    
    return stocks
```

---

## 三、数据需求

需要获取每只股票的**流通市值**（circulating_market_cap）：

```python
# 从stock_anomaly表获取
SELECT 
    a.id,
    a.stock_code,
    a.stock_name,
    a.anomaly_time,
    a.continuous_zt,
    a.circulating_market_cap,  -- 需要这个字段
    r.role,
    r.confidence_contribution
FROM stock_anomaly_mainline_rel r
JOIN stock_anomaly a ON r.anomaly_id = a.id
WHERE r.mainline_id = :mainline_id
```

**字段检查**：需要确认 `stock_anomaly` 表是否有 `circulating_market_cap` 字段。

---

## 四、实施步骤

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 1 | 检查 `circulating_market_cap` 字段是否存在 | 5分钟 |
| 2 | 修改 `_get_mainline_all_stocks()` 获取市值 | 10分钟 |
| 3 | 修改 `_recalculate_roles_by_rule()` 支持细分 | 20分钟 |
| 4 | 修改 `_update_mainlines_with_role_recalc()` 支持AI保留逻辑 | 20分钟 |
| 5 | 测试验证 | 30分钟 |
| **总计** | | **约1.5小时** |

---

## 五、预期效果

### 场景1: AI已定义龙头

```
主线: 半导体材料国产替代
AI定义: 603650 彤程新材 = 板块中军

处理结果:
- 603650 彤程新材: 板块中军 (保留AI定义)
- 其他股票按时间重新计算:
  - 002138 顺络电子(9:31:03): 补涨 (第1只非龙头)
  - 601133 柏诚股份(9:32:45): 跟风 (第2只非龙头)
  - ...
```

### 场景2: AI未定义龙头

```
主线: AI应用与智能体
AI定义: 无龙头（全是跟风/补涨）

处理结果（按时间+市值）:
- 300624 万兴科技(9:30:15, 市值180亿): 小盘情绪龙 (第1只)
- 300229 拓尔思(9:31:20, 市值220亿): 补涨 (第2只)
- 300418 昆仑万维(9:32:10, 市值350亿): 补涨 (第3只)
- ...其他: 跟风
```

---

## 六、关键问题

### Q1: 如果AI定义的"龙头"是多只怎么办？
**A**: 取AI评分最高的那只作为真龙头，其他降为补涨。

### Q2: 如果AI定义的龙头涨停时间很晚怎么办？
**A**: 保留AI定义，因为AI可能基于逻辑正宗性判定（如科大讯飞虽然涨停晚，但是真龙头）。

### Q3: 流通市值字段不存在怎么办？
**A**: 需要先从其他表获取（如 `ztb_day` 或实时行情表），或暂时用固定阈值（如用价格*流通股本估算）。

---

## 七、待确认

1. **流通市值字段**: `stock_anomaly` 表是否有 `circulating_market_cap`？如果没有，从哪获取？
2. **市值阈值**: 权重龙头>500亿、板块中军200-500亿、小盘<200亿，是否需要调整？
3. **AI保留策略**: 是否保留所有AI定义的role（包括补涨/跟风），还是只保留龙头？

请确认以上问题，我将立即实施方案。
