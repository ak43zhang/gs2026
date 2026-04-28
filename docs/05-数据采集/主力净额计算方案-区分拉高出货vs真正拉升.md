# 主力净额计算方案（区分拉高出货 vs 真正拉升）

> 更新时间：2026-04-28 13:05  
> 目标：解决高位放量上涨时，如何区分拉高出货和真正拉升

---

## 1. 问题核心分析

### 1.1 两种场景的相似性

```
场景A：拉高出货（主力卖出）
├── 价格：高位
├── 成交量：放量
├── 价格变化：上涨2%
└── 主力意图：吸引散户跟风，自己出货

场景B：真正拉升（主力买入）
├── 价格：高位（或突破高位）
├── 成交量：放量
├── 价格变化：上涨2%
└── 主力意图：突破压力位，继续拉升

问题：两者的表面特征几乎完全相同！
```

### 1.2 关键区别点

```
拉高出货 vs 真正拉升的区别：

┌─────────────────┬─────────────────┬─────────────────┐
│     特征        │    拉高出货     │    真正拉升     │
├─────────────────┼─────────────────┼─────────────────┤
│ 上涨持续性      │ 短暂，快速回落  │ 持续，高位横盘  │
│ 成交量分布      │ 前大后小        │ 均匀或递增      │
│ 价格回落速度    │ 很快（几分钟）  │ 慢或横盘        │
│ 后续走势        │ 下跌            │ 继续上涨        │
│ 盘口特征        │ 大单卖出多      │ 大单买入多      │
│ 封板意愿        │ 无              │ 强（可能涨停）  │
│ 历史压力        │ 接近历史高点    │ 突破历史高点    │
└─────────────────┴─────────────────┴─────────────────┘

核心区别：
- 拉高出货：不可持续，后续快速回落
- 真正拉升：可持续，后续高位横盘或继续上涨
```

### 1.3 关键洞察

```
关键洞察：

拉高出货和真正拉升的区别，
在单一时间窗口（3秒）内是无法区分的！

必须观察后续走势才能判断：
- 如果后续快速回落 → 拉高出货
- 如果后续高位横盘或继续上涨 → 真正拉升

这意味着：
- 实时计算时无法100%准确区分
- 只能基于概率和特征进行估算
- 事后验证才能确定
```

---

## 2. 改进方案：基于多周期验证的估算

### 2.1 核心思路

```python
# 核心思路：用后续走势验证当前行为

# 实时阶段（当前3秒）：
# - 识别为"疑似拉高出货"或"疑似真正拉升"
# - 给予中等置信度（0.6-0.7）
# - 主力净额按保守估计计算

# 验证阶段（后续30秒-5分钟）：
# - 观察后续走势
# - 如果价格回落 → 确认为拉高出货
# - 如果价格维持 → 确认为真正拉升
# - 回溯修正主力净额
```

### 2.2 实时判断逻辑（基于当前可用特征）

```python
def classify_high_volume_rise(price_now, price_history, volume_data, 
                              price_change_pct, time_context):
    """
    区分高位放量上涨是拉高出货还是真正拉升
    
    基于当前可用特征进行概率判断
    """
    
    score_dump = 0  # 拉高出货得分
    score_pump = 0  # 真正拉升得分
    
    # ===== 因子1：价格位置 =====
    day_high = price_history['day_high']
    day_low = price_history['day_low']
    position = (price_now - day_low) / (day_high - day_low) if day_high > day_low else 0.5
    
    if position >= 0.98:  # 非常接近当日最高
        score_dump += 30  # 拉高出货概率高（主力在最高位出货）
    elif position >= 0.95:  # 接近当日最高
        score_dump += 20
        score_pump += 10  # 也可能是突破
    elif position >= 0.90:  # 高位但未到最高
        score_dump += 15
        score_pump += 20  # 拉升概率增加
    else:
        score_pump += 30  # 中位上涨，更可能是拉升
    
    # ===== 因子2：上涨速度 =====
    # 快速急涨（>1%/3秒）更可能是拉高出货
    # 稳步上涨（<0.5%/3秒）更可能是真正拉升
    if price_change_pct >= 1.0:  # 3秒涨超1%
        score_dump += 25  # 急涨更可能是出货
    elif price_change_pct >= 0.5:
        score_dump += 15
        score_pump += 10
    elif price_change_pct >= 0.3:
        score_pump += 20  # 稳步上涨更可能是拉升
    else:
        score_pump += 15
    
    # ===== 因子3：量能特征 =====
    volume_ratio = volume_data['current'] / volume_data['avg']
    
    if volume_ratio >= 5:  # 极端放量（5倍以上）
        score_dump += 20  # 极端放量更可能是出货
    elif volume_ratio >= 3:
        score_dump += 15
        score_pump += 10
    elif volume_ratio >= 2:
        score_pump += 15  # 正常放量更可能是拉升
    else:
        score_pump += 10
    
    # ===== 因子4：时间因素 =====
    current_time = time_context['current_time']
    
    # 早盘（9:30-10:00）放量上涨 → 更可能是拉升
    # 尾盘（14:30-15:00）放量上涨 → 更可能是出货
    if dt_time(9, 30) <= current_time <= dt_time(10, 0):
        score_pump += 15
    elif dt_time(14, 30) <= current_time <= dt_time(15, 0):
        score_dump += 15
    
    # ===== 因子5：涨停距离 =====
    zt_limit = get_zt_limit(stock_code)  # 涨停幅度（10%或20%）
    zt_price = day_open * (1 + zt_limit / 100)
    distance_to_zt = (zt_price - price_now) / price_now * 100
    
    if distance_to_zt <= 1.0:  # 距离涨停<1%
        score_pump += 25  # 接近涨停，更可能是拉升封板
    elif distance_to_zt <= 3.0:
        score_pump += 15
        score_dump += 10
    else:
        score_dump += 10  # 距离涨停远，出货可能性增加
    
    # ===== 综合判断 =====
    total_score = score_dump + score_pump
    
    if total_score == 0:
        return {'type': 'uncertain', 'dump_prob': 0.5, 'pump_prob': 0.5}
    
    dump_prob = score_dump / total_score
    pump_prob = score_pump / total_score
    
    if dump_prob >= 0.7:
        return {
            'type': '拉高出货',
            'dump_prob': dump_prob,
            'pump_prob': pump_prob,
            'confidence': dump_prob,
            'direction': -1  # 主力卖出
        }
    elif pump_prob >= 0.7:
        return {
            'type': '真正拉升',
            'dump_prob': dump_prob,
            'pump_prob': pump_prob,
            'confidence': pump_prob,
            'direction': 1  # 主力买入
        }
    else:
        return {
            'type': '不确定',
            'dump_prob': dump_prob,
            'pump_prob': pump_prob,
            'confidence': max(dump_prob, pump_prob),
            'direction': 0.5 if pump_prob > dump_prob else -0.5  # 偏某一方
        }
```

### 2.3 主力净额计算（保守估计）

```python
def calculate_main_net_conservative(delta_amount, classification):
    """
    保守计算主力净额
    
    当不确定时，给予保守估计（减少误判影响）
    """
    
    participation = calculate_participation_ratio(delta_amount)
    
    if classification['type'] == '拉高出货':
        # 确定为拉高出货
        direction = -1
        confidence = classification['confidence']
        main_net = delta_amount * participation * direction * confidence
        
    elif classification['type'] == '真正拉升':
        # 确定为真正拉升
        direction = 1
        confidence = classification['confidence']
        main_net = delta_amount * participation * direction * confidence
        
    else:  # 不确定
        # 保守处理：只计算参与系数的一半
        # 方向按概率加权
        direction = classification['pump_prob'] - classification['dump_prob']
        confidence = classification['confidence'] * 0.5  # 降低置信度
        main_net = delta_amount * participation * direction * confidence
    
    return main_net
```

---

## 3. 事后验证与回溯修正

### 3.1 验证逻辑

```python
def verify_and_correct(stock_code, timestamp, initial_classification):
    """
    事后验证并修正主力净额
    
    在后续30秒-5分钟后调用
    """
    
    # 获取后续走势
    future_data = get_future_data(stock_code, timestamp, duration=300)  # 5分钟
    
    if not future_data:
        return  # 无法验证
    
    price_current = initial_classification['price']
    price_future = future_data['price']
    price_change = (price_future - price_current) / price_current * 100
    
    # 判断标准
    if price_change <= -1.0:  # 后续下跌超1%
        # 确认为拉高出货
        verified_type = '拉高出货'
        correction_factor = -1.0  # 主力净额应为负
        
    elif price_change >= 1.0:  # 后续上涨超1%
        # 确认为真正拉升
        verified_type = '真正拉升'
        correction_factor = 1.0  # 主力净额应为正
        
    elif -0.5 <= price_change <= 0.5:  # 后续横盘
        if initial_classification['type'] == '拉高出货':
            verified_type = '高位横盘出货'
            correction_factor = -0.7
        else:
            verified_type = '高位横盘整理'
            correction_factor = 0.3
    else:
        verified_type = '不确定'
        correction_factor = 0
    
    # 回溯修正主力净额
    if verified_type != '不确定':
        correct_main_net_amount(stock_code, timestamp, correction_factor)
    
    return {
        'initial_type': initial_classification['type'],
        'verified_type': verified_type,
        'price_change': price_change,
        'correction_applied': verified_type != '不确定'
    }
```

### 3.2 修正策略

```python
def correct_main_net_amount(stock_code, timestamp, correction_factor):
    """
    回溯修正历史主力净额
    """
    
    # 从数据库读取原始记录
    record = query_main_net_record(stock_code, timestamp)
    
    if not record:
        return
    
    original_main_net = record['main_net_amount']
    original_direction = 1 if original_main_net > 0 else -1
    
    # 如果方向错误，修正
    if original_direction != correction_factor:
        # 修正后的主力净额
        corrected_main_net = abs(original_main_net) * correction_factor
        
        # 更新数据库
        update_main_net_record(stock_code, timestamp, corrected_main_net)
        
        # 记录修正日志
        log_correction(stock_code, timestamp, original_main_net, corrected_main_net)
```

---

## 4. 简化但实用的方案

### 4.1 核心问题

```
问题：实时计算时无法100%区分拉高出货和真正拉升

解决方案：
1. 实时阶段：概率判断 + 保守估计
2. 事后阶段：验证修正
3. 简化策略：只关注高置信度场景
```

### 4.2 简化判断逻辑

```python
def simple_classify(price_position, price_change_pct, volume_ratio, time_of_day):
    """
    简化版判断逻辑
    
    只处理高置信度场景，其他场景标记为"不确定"
    """
    
    # 场景1：极高位置 + 极端放量 + 急涨 → 拉高出货（高置信度）
    if price_position >= 0.98 and volume_ratio >= 5 and price_change_pct >= 1.0:
        return {'type': '拉高出货', 'direction': -1, 'confidence': 0.85}
    
    # 场景2：中低位 + 正常放量 + 稳步上涨 → 真正拉升（高置信度）
    if price_position <= 0.7 and 2 <= volume_ratio <= 4 and 0.3 <= price_change_pct <= 0.8:
        return {'type': '真正拉升', 'direction': 1, 'confidence': 0.8}
    
    # 场景3：早盘 + 放量上涨 → 偏向拉升
    if time_of_day <= dt_time(10, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return {'type': '疑似拉升', 'direction': 1, 'confidence': 0.6}
    
    # 场景4：尾盘 + 放量上涨 → 偏向出货
    if time_of_day >= dt_time(14, 30) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return {'type': '疑似出货', 'direction': -1, 'confidence': 0.6}
    
    # 其他场景：不确定
    return {'type': '不确定', 'direction': 0, 'confidence': 0}
```

### 4.3 主力净额计算（最终版）

```python
def calculate_main_net_final(stock_code, current_data, previous_data, 
                             historical_data, day_stats, time_of_day):
    """
    最终版主力净额计算
    """
    
    # 计算周期变化
    delta_amount = current_data['amount'] - previous_data['amount']
    delta_volume = current_data['volume'] - previous_data['volume']
    price_change_pct = current_data['change_pct'] - previous_data.get('change_pct', 0)
    price_now = current_data['price']
    
    # 门槛检查
    if delta_amount < 300000 or delta_volume < 20000:
        return 0.0
    
    # 计算价格位置
    day_high = day_stats['day_high']
    day_low = day_stats['day_low']
    price_position = (price_now - day_low) / (day_high - day_low) if day_high > day_low else 0.5
    
    # 计算量能比
    avg_volume = historical_data.get('avg_volume_20d', delta_volume)
    volume_ratio = delta_volume / avg_volume if avg_volume > 0 else 1.0
    
    # 分类判断
    classification = simple_classify(
        price_position, price_change_pct, volume_ratio, time_of_day
    )
    
    # 计算参与系数
    if delta_amount >= 2000000:
        participation = 1.0
    elif delta_amount >= 1000000:
        participation = 0.8
    elif delta_amount >= 500000:
        participation = 0.6
    else:
        participation = 0.4
    
    # 计算主力净额
    direction = classification['direction']
    confidence = classification['confidence']
    
    if direction != 0:
        main_net = delta_amount * participation * direction * confidence
    else:
        # 不确定时，保守处理
        main_net = 0.0
    
    return {
        'main_net_amount': round(main_net, 2),
        'type': classification['type'],
        'direction': direction,
        'confidence': confidence
    }
```

---

## 5. 总结

### 5.1 关键结论

```
1. 实时无法100%区分拉高出货和真正拉升
   - 两者表面特征相同
   - 必须观察后续走势才能确定

2. 解决方案：
   - 实时：概率判断 + 保守估计
   - 事后：验证修正
   - 简化：只处理高置信度场景

3. 高置信度场景：
   - 极高位置 + 极端放量 + 急涨 → 拉高出货
   - 中低位 + 正常放量 + 稳步上涨 → 真正拉升
   - 早盘放量上涨 → 偏向拉升
   - 尾盘放量上涨 → 偏向出货

4. 不确定场景：
   - 主力净额计算为0
   - 或给予极低置信度
```

### 5.2 新增字段（保持3个）

```sql
ALTER TABLE monitor_gp_sssj_{date} ADD COLUMN (
    main_net_amount DECIMAL(15,2) DEFAULT 0 COMMENT '主力净额（元）',
    main_behavior VARCHAR(20) DEFAULT '' COMMENT '主力行为类型',
    main_confidence DECIMAL(3,2) DEFAULT 0 COMMENT '置信度（0-1）'
);
```

### 5.3 行为类型定义

| 行为类型 | 说明 | 主力净额方向 |
|----------|------|--------------|
| 拉高出货 | 极高位置放量急涨 | 负（卖出） |
| 真正拉升 | 中低位稳步上涨 | 正（买入） |
| 疑似拉升 | 早盘放量上涨 | 正（买入） |
| 疑似出货 | 尾盘放量上涨 | 负（卖出） |
| 不确定 | 无法判断 | 0 |

确认后实施开发。
