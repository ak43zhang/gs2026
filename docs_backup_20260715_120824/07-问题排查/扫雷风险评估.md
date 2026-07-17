# 通达信风险数据 (mine_clearance_tdx) 分析与隔夜超短风险评估

## 数据来源

```python
adata.sentiment.mine.mine_clearance_tdx(stock_code=dm)
```

## 返回数据结构分析

根据 `adata` 库和通达信数据的特点，`mine_clearance_tdx` 通常返回以下字段：

### 核心字段

| 字段名 | 类型 | 说明 | 风险权重 |
|--------|------|------|----------|
| `stock_code` | str | 股票代码 | - |
| `stock_name` | str | 股票名称 | - |
| `risk_type` | str | 风险类型 | 高 |
| `risk_level` | int/str | 风险等级 (1-5) | 高 |
| `risk_desc` | str | 风险描述 | 中 |
| `notice_date` | date | 公告日期 | 中 |
| `risk_reason` | str | 风险原因 | 高 |

### 常见风险类型

1. **ST风险** - 特别处理
2. ***ST风险** - 退市风险警示
3. **暂停上市风险** - 可能暂停交易
4. **退市风险** - 可能终止上市
5. **重大违法强制退市** - 违法退市
6. **其他风险警示** - 其他异常情况

## 风险等级定义

### 风险等级 5 (极高风险) - 隔夜超短禁止
- 已退市或即将退市
- 重大违法强制退市
- 暂停上市
- **建议**: 绝对禁止隔夜持仓

### 风险等级 4 (高风险) - 隔夜超短极度谨慎
- *ST股票（退市风险警示）
- 连续亏损且主营业务停滞
- 重大违法违规调查中
- **建议**: 不建议隔夜持仓，如必须持仓，仓位<10%

### 风险等级 3 (中等风险) - 隔夜超短需谨慎
- ST股票（特别处理）
- 连续亏损但主营业务正常
- 重大诉讼或仲裁
- **建议**: 可隔夜持仓，但仓位<30%，设置止损

### 风险等级 2 (低风险) - 隔夜超短可接受
- 一般风险警示
- 业绩预亏或预减
- 股东减持
- **建议**: 可正常隔夜持仓，注意仓位控制

### 风险等级 1 (极低风险) - 隔夜超短安全
- 无特殊风险
- 正常经营
- **建议**: 可正常隔夜持仓

## 隔夜超短风险评估模型

### 评分公式

```python
def calculate_overnight_risk_score(risk_data):
    """
    计算隔夜超短风险评分
    分数越高，风险越大
    """
    base_score = 0
    
    # 风险等级权重
    risk_level_weights = {
        5: 100,  # 极高风险
        4: 80,   # 高风险
        3: 50,   # 中等风险
        2: 20,   # 低风险
        1: 0     # 极低风险
    }
    
    # 基础风险分
    base_score += risk_level_weights.get(risk_data['risk_level'], 50)
    
    # 风险类型加成
    risk_type_bonus = {
        '退市': 50,
        '暂停上市': 40,
        '重大违法': 40,
        '*ST': 30,
        'ST': 20,
        '立案调查': 25,
        '重大诉讼': 15,
        '业绩预亏': 10,
        '股东减持': 5
    }
    
    for risk_type, bonus in risk_type_bonus.items():
        if risk_type in str(risk_data.get('risk_type', '')):
            base_score += bonus
            break
    
    # 时间因子（越新的风险越严重）
    if 'notice_date' in risk_data:
        days_since_notice = (datetime.now() - risk_data['notice_date']).days
        if days_since_notice <= 3:
            base_score *= 1.2  # 3天内公告的风险加重
        elif days_since_notice <= 7:
            base_score *= 1.1  # 一周内公告的风险略加重
    
    return min(base_score, 100)  # 最高100分
```

### 风险等级划分

| 总分 | 风险等级 | 隔夜超短建议 | 最大仓位 |
|------|----------|--------------|----------|
| 0-20 | 🟢 安全 | 可正常持仓 | 100% |
| 21-40 | 🟡 低风险 | 可持仓，注意止损 | 70% |
| 41-60 | 🟠 中等风险 | 谨慎持仓 | 40% |
| 61-80 | 🔴 高风险 | 不建议持仓 | 10% |
| 81-100 | ⚫ 极高风险 | 禁止持仓 | 0% |

## 隔夜超短决策流程

```
获取风险数据
    ↓
计算风险评分
    ↓
评分 ≤ 20? → 🟢 安全持仓
    ↓ 否
评分 ≤ 40? → 🟡 轻仓持仓
    ↓ 否
评分 ≤ 60? → 🟠 谨慎持仓
    ↓ 否
评分 ≤ 80? → 🔴 不建议持仓
    ↓ 否
评分 > 80? → ⚫ 禁止持仓
```

## 实际应用代码

```python
import pandas as pd
import adata
from datetime import datetime

def analyze_overnight_risk(stock_code):
    """
    分析股票隔夜超短风险
    
    Args:
        stock_code: 股票代码
        
    Returns:
        dict: 风险分析结果
    """
    # 获取通达信风险数据
    df_risk = adata.sentiment.mine.mine_clearance_tdx(stock_code=stock_code)
    
    if df_risk.empty:
        return {
            'stock_code': stock_code,
            'risk_score': 0,
            'risk_level': '安全',
            'can_overnight': True,
            'max_position': 1.0,
            'reason': '无风险数据，默认安全'
        }
    
    # 取最新风险数据
    latest_risk = df_risk.iloc[0]
    
    # 计算风险评分
    risk_score = calculate_overnight_risk_score(latest_risk)
    
    # 确定风险等级和建议
    if risk_score <= 20:
        risk_level = '🟢 安全'
        can_overnight = True
        max_position = 1.0
    elif risk_score <= 40:
        risk_level = '🟡 低风险'
        can_overnight = True
        max_position = 0.7
    elif risk_score <= 60:
        risk_level = '🟠 中等风险'
        can_overnight = True
        max_position = 0.4
    elif risk_score <= 80:
        risk_level = '🔴 高风险'
        can_overnight = False
        max_position = 0.1
    else:
        risk_level = '⚫ 极高风险'
        can_overnight = False
        max_position = 0.0
    
    return {
        'stock_code': stock_code,
        'stock_name': latest_risk.get('stock_name', ''),
        'risk_score': risk_score,
        'risk_level': risk_level,
        'can_overnight': can_overnight,
        'max_position': max_position,
        'risk_type': latest_risk.get('risk_type', ''),
        'risk_desc': latest_risk.get('risk_desc', ''),
        'notice_date': latest_risk.get('notice_date', ''),
        'reason': f"风险类型: {latest_risk.get('risk_type', '')}, 描述: {latest_risk.get('risk_desc', '')}"
    }


# 批量分析
stock_list = ['000001', '000002', '600000']  # 示例股票列表
results = []

for code in stock_list:
    result = analyze_overnight_risk(code)
    results.append(result)

df_result = pd.DataFrame(results)
print(df_result[['stock_code', 'stock_name', 'risk_level', 'can_overnight', 'max_position']])
```

## 注意事项

1. **数据时效性**: 风险数据每日更新，隔夜前必须重新检查
2. **组合风险**: 多只股票持仓时，风险评分应加权平均
3. **市场环境**: 大盘系统性风险可能放大个股风险
4. **黑天鹅事件**: 模型无法预测突发重大事件
5. **建议结合**: 应结合技术分析、资金流向等多维度判断

## 总结

| 风险等级 | 隔夜超短建议 | 关键指标 |
|----------|--------------|----------|
| 🟢 安全 (0-20分) | 可正常持仓 | 无ST/*ST，无重大风险 |
| 🟡 低风险 (21-40分) | 可持仓，注意止损 | 一般风险警示 |
| 🟠 中等风险 (41-60分) | 谨慎持仓 | ST股票，业绩预亏 |
| 🔴 高风险 (61-80分) | 不建议持仓 | *ST股票，立案调查 |
| ⚫ 极高风险 (81-100分) | 禁止持仓 | 退市风险，重大违法 |

**核心原则**: 隔夜超短首要原则是风险控制，宁可错过，不可做错。
