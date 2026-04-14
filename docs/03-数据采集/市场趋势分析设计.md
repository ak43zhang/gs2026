# 大盘趋势分析系统设计方案

> 设计时间: 2026-03-31 11:06  
> 目标: 基于 monitor_gp_apqd_{date} 表设计大盘趋势判断系统

---

## 一、现状分析

### 1.1 现有数据结构

**monitor_gp_apqd_{date}** (大盘强度表)
```
字段说明:
- time: 时间戳 HH:MM:SS
- cur_up: 当前上涨家数
- cur_down: 当前下跌家数
- cur_up_ratio: 当前上涨比例 (%)
- cur_down_ratio: 当前下跌比例 (%)
- cur_up_down_ratio: 当前涨跌比
- min_up: 分钟上涨家数变化
- min_down: 分钟下跌家数变化
- min_up_ratio: 分钟上涨比例 (%)
- strength_score: 强度评分 (0-100)
- state: 市场状态 (极强/强/温和/弱/极弱)
- signal: 转换信号 (弱转强/强转弱/无)
```

### 1.2 现有判断逻辑

```python
def judge_market_strength(stats_row):
    # 1. 基础评分 (0-100)
    base_score = cur_up_ratio
    
    # 2. 趋势修正
    trend_score = (min_up_ratio - 50) * 0.8
    
    # 3. 强度评分
    strength_score = base_score + trend_score
    
    # 4. 状态划分
    if strength_score >= 80: state = "极强"
    elif strength_score >= 60: state = "强"
    elif strength_score <= 20: state = "极弱"
    elif strength_score <= 40: state = "弱"
    else: state = "温和"
    
    # 5. 转换信号
    if cur_up_ratio <= 40 and min_up_ratio > 55: signal = "弱转强"
    elif cur_up_ratio >= 60 and min_down_ratio > 55: signal = "强转弱"
```

### 1.3 现有问题

| 问题 | 说明 |
|------|------|
| 单点判断 | 只基于当前时刻，缺乏趋势连续性 |
| 噪音敏感 | 分钟级波动导致信号频繁变化 |
| 缺乏预测 | 只能判断当前状态，无法预测趋势 |
| 维度单一 | 只考虑涨跌家数，缺乏成交量、资金流向等 |

---

## 二、趋势分析模型设计

### 2.1 多维度指标体系

```
┌─────────────────────────────────────────────────────────┐
│                    大盘趋势分析模型                       │
├─────────────────────────────────────────────────────────┤
│  维度1: 市场情绪        维度2: 趋势强度                  │
│  - 上涨家数占比         - N分钟移动平均线                │
│  - 涨跌比               - 趋势斜率                       │
│  - 涨跌停家数           - 加速度                         │
├─────────────────────────────────────────────────────────┤
│  维度3: 资金流向        维度4: 波动率                    │
│  - 主力资金流向         - 价格振幅                       │
│  - 成交量变化           - 波动率指数                     │
│  - 换手率               - 恐慌/贪婪指数                  │
├─────────────────────────────────────────────────────────┤
│                    综合趋势评分                          │
│         走强 / 走弱 / 震荡 / 不确定                      │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心算法设计

#### 算法1: 移动平均线趋势判断

```python
def calculate_trend_ma(apqd_data, window=5):
    """
    基于移动平均线判断趋势
    
    Args:
        apqd_data: monitor_gp_apqd 历史数据 DataFrame
        window: 移动平均窗口（默认5分钟）
    
    Returns:
        trend: 'rising' | 'falling' | 'flat'
        confidence: 置信度 (0-1)
    """
    # 计算强度评分的移动平均线
    apqd_data['ma'] = apqd_data['strength_score'].rolling(window=window).mean()
    
    # 计算斜率
    recent = apqd_data.tail(window)
    slope = np.polyfit(range(len(recent)), recent['ma'], 1)[0]
    
    # 判断趋势
    if slope > 2:
        trend = 'rising'  # 走强
        confidence = min(abs(slope) / 10, 1.0)
    elif slope < -2:
        trend = 'falling'  # 走弱
        confidence = min(abs(slope) / 10, 1.0)
    else:
        trend = 'flat'  # 震荡
        confidence = 1.0 - min(abs(slope) / 2, 1.0)
    
    return trend, confidence
```

#### 算法2: 多时间框架趋势融合

```python
def multi_timeframe_trend(apqd_data):
    """
    多时间框架趋势融合
    
    短期(5分钟) + 中期(15分钟) + 长期(30分钟)
    """
    trends = {}
    
    # 短期趋势
    trends['short'] = calculate_trend_ma(apqd_data, window=5)
    
    # 中期趋势
    trends['medium'] = calculate_trend_ma(apqd_data, window=15)
    
    # 长期趋势
    trends['long'] = calculate_trend_ma(apqd_data, window=30)
    
    # 融合判断
    if trends['short'][0] == trends['medium'][0] == trends['long'][0]:
        # 三个周期一致，高置信度
        return trends['short'][0], 0.9
    elif trends['medium'][0] == trends['long'][0]:
        # 中长期一致，跟随中长期
        return trends['medium'][0], 0.7
    else:
        # 不一致，震荡
        return 'uncertain', 0.5
```

#### 算法3: 动量指标判断

```python
def calculate_momentum_signals(apqd_data):
    """
    计算动量指标
    
    Returns:
        {
            'momentum_score': 动量评分 (-100 to 100),
            'rsi': 相对强弱指标,
            'macd': MACD信号,
            'overbought_oversold': 超买超卖状态
        }
    """
    scores = apqd_data['strength_score'].values
    
    # RSI计算
    delta = np.diff(scores)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = np.mean(gain[-14:])
    avg_loss = np.mean(loss[-14:])
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    
    # 动量评分
    momentum_score = (rsi - 50) * 2  # 映射到 -100 ~ 100
    
    # 超买超卖判断
    if rsi > 70:
        overbought_oversold = 'overbought'  # 超买，可能回调
    elif rsi < 30:
        overbought_oversold = 'oversold'  # 超卖，可能反弹
    else:
        overbought_oversold = 'neutral'
    
    return {
        'momentum_score': momentum_score,
        'rsi': rsi,
        'overbought_oversold': overbought_oversold
    }
```

#### 算法4: 综合趋势评分

```python
def comprehensive_trend_analysis(apqd_data, market_data=None):
    """
    综合趋势分析
    
    融合多个维度给出最终趋势判断
    """
    # 1. 趋势方向 (40%)
    trend_direction, trend_confidence = multi_timeframe_trend(apqd_data)
    
    # 2. 动量指标 (30%)
    momentum = calculate_momentum_signals(apqd_data)
    
    # 3. 市场情绪 (20%)
    latest = apqd_data.iloc[-1]
    sentiment_score = (
        latest['cur_up_ratio'] * 0.5 +
        (100 - latest['cur_down_ratio']) * 0.5
    )
    
    # 4. 波动率 (10%)
    volatility = apqd_data['strength_score'].std()
    
    # 综合评分 (-100 to 100)
    final_score = (
        trend_confidence * (1 if trend_direction == 'rising' else -1 if trend_direction == 'falling' else 0) * 40 +
        momentum['momentum_score'] * 0.3 +
        (sentiment_score - 50) * 2 * 0.2 -
        volatility * 0.1
    )
    
    # 趋势判断
    if final_score > 30:
        trend = '走强'
        description = '大盘处于上升趋势，建议积极操作'
    elif final_score < -30:
        trend = '走弱'
        description = '大盘处于下降趋势，建议谨慎防守'
    elif -10 <= final_score <= 10:
        trend = '震荡'
        description = '大盘处于震荡整理阶段，建议观望'
    else:
        trend = '不确定'
        description = '趋势不明朗，等待方向选择'
    
    return {
        'trend': trend,
        'score': round(final_score, 2),
        'confidence': round(abs(final_score) / 100, 2),
        'description': description,
        'details': {
            'trend_direction': trend_direction,
            'momentum': momentum,
            'sentiment_score': round(sentiment_score, 2),
            'volatility': round(volatility, 2)
        }
    }
```

---

## 三、系统架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    大盘趋势分析系统                       │
├─────────────────────────────────────────────────────────┤
│  数据采集层                                              │
│  - monitor_gp_apqd_{date} (大盘强度)                    │
│  - monitor_gp_sssj_{date} (实时行情)                    │
│  - 指数数据 (上证指数、深证成指等)                       │
├─────────────────────────────────────────────────────────┤
│  数据处理层                                              │
│  - 数据清洗与标准化                                      │
│  - 特征工程 (技术指标计算)                               │
│  - 数据缓存 (Redis)                                     │
├─────────────────────────────────────────────────────────┤
│  趋势分析层                                              │
│  - 移动平均线分析                                        │
│  - 动量指标计算                                          │
│  - 多时间框架融合                                        │
│  - 综合评分模型                                          │
├─────────────────────────────────────────────────────────┤
│  应用服务层                                              │
│  - API接口 (/api/market/trend)                          │
│  - 实时推送 (WebSocket)                                 │
│  - 历史查询                                             │
├─────────────────────────────────────────────────────────┤
│  展示层                                                  │
│  - Dashboard2 集成                                       │
│  - 趋势图表                                             │
│  - 信号提醒                                             │
└─────────────────────────────────────────────────────────┘
```

### 3.2 数据表设计

**新增表: market_trend_analysis**

```sql
CREATE TABLE market_trend_analysis (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 时间信息
    created_at DATETIME NOT NULL,
    analysis_date DATE NOT NULL,
    analysis_time TIME NOT NULL,
    
    -- 趋势判断
    trend VARCHAR(20) NOT NULL COMMENT '趋势: 走强/走弱/震荡/不确定',
    trend_score DECIMAL(5,2) COMMENT '趋势评分 (-100 to 100)',
    confidence DECIMAL(3,2) COMMENT '置信度 (0-1)',
    description TEXT COMMENT '趋势描述',
    
    -- 详细指标 (JSON存储)
    indicators JSON COMMENT '详细指标: {
        "ma_short": {"trend": "rising", "slope": 3.5},
        "ma_medium": {"trend": "rising", "slope": 2.1},
        "ma_long": {"trend": "flat", "slope": 0.5},
        "rsi": 65.5,
        "momentum_score": 31.0,
        "sentiment_score": 58.5,
        "volatility": 8.2
    }',
    
    -- 原始数据引用
    apqd_data_time VARCHAR(8) COMMENT '基于哪个时间点的APQD数据',
    
    -- 索引
    INDEX idx_analysis_date (analysis_date),
    INDEX idx_created_at (created_at),
    INDEX idx_trend (trend)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大盘趋势分析结果表';
```

---

## 四、API设计

### 4.1 实时趋势查询

```python
@market_bp.route('/api/market/trend', methods=['GET'])
def get_market_trend():
    """
    获取当前大盘趋势分析
    
    Query Params:
        date: 日期 YYYYMMDD，默认今天
        
    Returns:
        {
            "success": true,
            "data": {
                "trend": "走强",
                "score": 45.5,
                "confidence": 0.85,
                "description": "大盘处于上升趋势，建议积极操作",
                "timestamp": "2026-03-31 10:30:00",
                "indicators": {
                    "ma_short": {"trend": "rising", "slope": 3.5, "window": 5},
                    "ma_medium": {"trend": "rising", "slope": 2.1, "window": 15},
                    "ma_long": {"trend": "flat", "slope": 0.5, "window": 30},
                    "rsi": 65.5,
                    "momentum_score": 31.0,
                    "sentiment_score": 58.5,
                    "volatility": 8.2
                },
                "signals": [
                    {"type": "weak_to_strong", "message": "弱转强信号", "time": "10:25:00"}
                ]
            }
        }
    """
```

### 4.2 历史趋势查询

```python
@market_bp.route('/api/market/trend/history', methods=['GET'])
def get_market_trend_history():
    """
    获取历史趋势数据
    
    Query Params:
        date: 日期 YYYYMMDD
        start_time: 开始时间 HH:MM:SS
        end_time: 结束时间 HH:MM:SS
        
    Returns:
        趋势变化时间序列
    """
```

### 4.3 趋势预警

```python
@market_bp.route('/api/market/trend/alerts', methods=['GET'])
def get_market_alerts():
    """
    获取趋势预警信号
    
    当趋势发生重要变化时触发:
    - 弱转强
    - 强转弱
    - 进入超买区
    - 进入超卖区
    """
```

---

## 五、前端展示设计

### 5.1 趋势仪表盘

```html
<!-- 大盘趋势卡片 -->
<div class="market-trend-card">
    <div class="trend-header">
        <h3>📊 大盘趋势</h3>
        <span class="trend-badge trend-{{trend}}">{{trend}}</span>
    </div>
    
    <div class="trend-score">
        <div class="score-value">{{score}}</div>
        <div class="score-bar">
            <div class="score-fill" style="width: {{score + 100}}%"></div>
        </div>
        <div class="confidence">置信度: {{confidence * 100}}%</div>
    </div>
    
    <div class="trend-description">
        {{description}}
    </div>
    
    <div class="trend-indicators">
        <div class="indicator">
            <span class="label">短期趋势</span>
            <span class="value {{ma_short.trend}}">{{ma_short.trend}}</span>
        </div>
        <div class="indicator">
            <span class="label">中期趋势</span>
            <span class="value {{ma_medium.trend}}">{{ma_medium.trend}}</span>
        </div>
        <div class="indicator">
            <span class="label">RSI</span>
            <span class="value">{{rsi}}</span>
        </div>
    </div>
</div>

<!-- 趋势图表 -->
<div class="trend-chart">
    <canvas id="trendChart"></canvas>
</div>
```

### 5.2 趋势颜色标识

| 趋势 | 颜色 | 说明 |
|------|------|------|
| 走强 | 🟢 绿色 | 积极做多 |
| 走弱 | 🔴 红色 | 谨慎防守 |
| 震荡 | 🟡 黄色 | 观望等待 |
| 不确定 | ⚪ 灰色 | 方向不明 |

---

## 六、实施计划

### 阶段1: 核心算法实现 (60分钟)
- [ ] 实现移动平均线趋势计算
- [ ] 实现动量指标计算
- [ ] 实现多时间框架融合
- [ ] 实现综合评分模型

### 阶段2: 数据服务层 (45分钟)
- [ ] 创建 market_trend_service.py
- [ ] 实现数据读取和缓存
- [ ] 实现趋势分析API

### 阶段3: API和前端 (45分钟)
- [ ] 创建 market_trend_routes.py
- [ ] 实现前端趋势卡片
- [ ] 实现趋势图表

### 阶段4: 测试优化 (30分钟)
- [ ] 历史数据回测
- [ ] 参数调优
- [ ] 性能测试

**总计: 180分钟**

---

## 七、效果预期

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 趋势判断准确率 | ~60% | ~75% |
| 信号噪音比 | 1:3 | 1:1.5 |
| 预测提前量 | 实时 | 5-15分钟 |
| 用户决策支持 | 单点 | 多维度 |

---

**文档位置**: `docs/market_trend_analysis_design.md`

**请确认方案后实施。**
