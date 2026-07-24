# 大盘概览"上涨下跌比"字段设计方案

## 需求概述

在大盘概览中增加"上涨下跌比"字段，用于确定当天大盘整体涨跌情况。

**计算公式**: `实体上涨数量 / 实体下跌数量`

---

## 关键概念澄清

### 现有字段 vs 新增字段

| 字段 | 现有含义 | 新增含义 |
|------|----------|----------|
| `cur_up_down_ratio` | **分钟涨跌比**: 当前时刻 vs 上一时刻的变化 | 保持不变 |
| `entity_up_down_ratio` | **新增**: 当天累计实体上涨 / 实体下跌 | 本次新增 |

**区别**:
- `cur_up_down_ratio`: 反映短期 momentum（3秒内变化）
- `entity_up_down_ratio`: 反映全天趋势（从开盘到当前累计）

---

## 计算逻辑

### 实体上涨/下跌定义

```python
# 实体上涨: 当天累计涨跌幅 > 0
entity_up = change_pct > 0

# 实体下跌: 当天累计涨跌幅 < 0  
entity_down = change_pct < 0

# 平盘: 当天累计涨跌幅 == 0
entity_flat = change_pct == 0
```

### 计算公式

```python
entity_up_count = sum(change_pct > 0)
entity_down_count = sum(change_pct < 0)
entity_flat_count = sum(change_pct == 0)

entity_up_down_ratio = entity_up_count / entity_down_count
                           if entity_down_count > 0 
                           else float('inf')  # 无下跌时设为无穷大
```

### 示例

```
时间: 10:30:00
股票数据:
  股票A: change_pct = +2.5%  → 实体上涨
  股票B: change_pct = -1.2%  → 实体下跌
  股票C: change_pct = +0.8%  → 实体上涨
  股票D: change_pct = 0%     → 平盘
  股票E: change_pct = -3.1%  → 实体下跌

计算:
  entity_up_count = 2 (A, C)
  entity_down_count = 2 (B, E)
  entity_flat_count = 1 (D)
  
  entity_up_down_ratio = 2 / 2 = 1.0
  
解读:
  - ratio = 1.0: 上涨下跌平衡
  - ratio > 1.0: 上涨多于下跌（多头占优）
  - ratio < 1.0: 下跌多于上涨（空头占优）
  - ratio > 2.0: 明显多头市场
  - ratio < 0.5: 明显空头市场
```

---

## 实施方案

### 方案1：修改 get_market_stats_v2 函数（推荐）⭐

**文件**: `src/gs2026/monitor/monitor_stock.py`

**位置**: `get_market_stats_v2` 函数（第 1655 行附近）

**修改内容**:

```python
def get_market_stats_v2(df_now: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    【优化版】计算当前时刻的大盘统计以及前一分钟的大盘统计
    【新增】计算实体上涨下跌比（entity_up_down_ratio）
    """
    # ... 原有代码 ...
    
    # ---------- 1. 当前统计（原有逻辑）----------
    # ...
    
    # 【新增】计算实体上涨下跌比
    # 实体上涨: change_pct > 0
    # 实体下跌: change_pct < 0
    entity_up_mask = df_now['change_pct'] > 0
    entity_down_mask = df_now['change_pct'] < 0
    entity_flat_mask = df_now['change_pct'] == 0
    
    entity_up_count = entity_up_mask.sum()
    entity_down_count = entity_down_mask.sum()
    entity_flat_count = entity_flat_mask.sum()
    
    # 计算实体上涨下跌比
    if entity_down_count > 0:
        entity_up_down_ratio = round(entity_up_count / entity_down_count, 2)
    else:
        entity_up_down_ratio = float('inf') if entity_up_count > 0 else 0.0
    
    # 计算实体上涨占比
    if total_cur > 0:
        entity_up_ratio = round(entity_up_count / total_cur * 100, 2)
        entity_down_ratio = round(entity_down_count / total_cur * 100, 2)
        entity_flat_ratio = round(entity_flat_count / total_cur * 100, 2)
    else:
        entity_up_ratio = entity_down_ratio = entity_flat_ratio = 0.0
    
    # ---------- 2. 分钟统计（原有逻辑）----------
    # ...
    
    # ---------- 3. 构建结果（新增字段）----------
    result = pd.DataFrame([{
        'time': time_value,
        # 原有字段...
        'cur_up': cur_stats['up'],
        'cur_down': cur_stats['down'],
        'cur_flat': cur_stats['flat'],
        'cur_total': total_cur,
        'cur_up_ratio': cur_ratios['up'],
        'cur_down_ratio': cur_ratios['down'],
        'cur_flat_ratio': cur_ratios['flat'],
        'cur_up_down_ratio': cur_ratios['up_down'],
        
        # 【新增】实体统计字段
        'entity_up': int(entity_up_count),
        'entity_down': int(entity_down_count),
        'entity_flat': int(entity_flat_count),
        'entity_up_ratio': entity_up_ratio,
        'entity_down_ratio': entity_down_ratio,
        'entity_flat_ratio': entity_flat_ratio,
        'entity_up_down_ratio': entity_up_down_ratio,
        
        # 分钟统计字段...
        'min_up': min_stats['up'],
        'min_down': min_stats['down'],
        # ...
    }])
    
    return result
```

---

### 方案2：新增独立计算函数（备选）

如果担心修改 `get_market_stats_v2` 影响原有逻辑，可以新增独立函数：

```python
def calculate_entity_up_down_ratio(df: pd.DataFrame) -> dict:
    """
    计算实体上涨下跌比
    
    Args:
        df: 包含 change_pct 列的 DataFrame
    
    Returns:
        dict: 包含实体统计数据的字典
    """
    if df is None or df.empty or 'change_pct' not in df.columns:
        return {
            'entity_up': 0,
            'entity_down': 0,
            'entity_flat': 0,
            'entity_up_ratio': 0.0,
            'entity_down_ratio': 0.0,
            'entity_flat_ratio': 0.0,
            'entity_up_down_ratio': 0.0,
        }
    
    # 确保 change_pct 为数值
    change_pct = pd.to_numeric(df['change_pct'], errors='coerce')
    total = len(change_pct.dropna())
    
    if total == 0:
        return {
            'entity_up': 0,
            'entity_down': 0,
            'entity_flat': 0,
            'entity_up_ratio': 0.0,
            'entity_down_ratio': 0.0,
            'entity_flat_ratio': 0.0,
            'entity_up_down_ratio': 0.0,
        }
    
    # 计算实体上涨/下跌/平盘
    entity_up = (change_pct > 0).sum()
    entity_down = (change_pct < 0).sum()
    entity_flat = (change_pct == 0).sum()
    
    # 计算比率
    entity_up_ratio = round(entity_up / total * 100, 2)
    entity_down_ratio = round(entity_down / total * 100, 2)
    entity_flat_ratio = round(entity_flat / total * 100, 2)
    
    # 计算上涨下跌比
    if entity_down > 0:
        entity_up_down_ratio = round(entity_up / entity_down, 2)
    else:
        entity_up_down_ratio = float('inf') if entity_up > 0 else 0.0
    
    return {
        'entity_up': int(entity_up),
        'entity_down': int(entity_down),
        'entity_flat': int(entity_flat),
        'entity_up_ratio': entity_up_ratio,
        'entity_down_ratio': entity_down_ratio,
        'entity_flat_ratio': entity_flat_ratio,
        'entity_up_down_ratio': entity_up_down_ratio,
    }

# 在 get_market_stats_v2 中调用
entity_stats = calculate_entity_up_down_ratio(df_now)

# 合并到结果
result = pd.DataFrame([{
    # ... 原有字段 ...
    **entity_stats,  # 展开实体统计字段
}])
```

---

### 方案3：债券监控同步修改

**文件**: `src/gs2026/monitor/monitor_bond.py`

**位置**: `deal_zq_works` 函数或新增债券大盘统计函数

**修改内容**:

```python
def calculate_bond_market_stats(df_now: pd.DataFrame) -> pd.DataFrame:
    """
    计算债券市场统计数据（类似股票）
    【新增】实体上涨下跌比
    """
    if df_now is None or df_now.empty:
        return pd.DataFrame()
    
    # 确保有 change_pct 列
    if 'change_pct' not in df_now.columns:
        logger.warning("债券数据缺少 change_pct 列，无法计算大盘统计")
        return pd.DataFrame()
    
    # 计算实体统计（复用股票逻辑）
    change_pct = pd.to_numeric(df_now['change_pct'], errors='coerce')
    total = len(change_pct.dropna())
    
    if total == 0:
        return pd.DataFrame()
    
    entity_up = (change_pct > 0).sum()
    entity_down = (change_pct < 0).sum()
    entity_flat = (change_pct == 0).sum()
    
    entity_up_ratio = round(entity_up / total * 100, 2)
    entity_down_ratio = round(entity_down / total * 100, 2)
    entity_flat_ratio = round(entity_flat / total * 100, 2)
    
    if entity_down > 0:
        entity_up_down_ratio = round(entity_up / entity_down, 2)
    else:
        entity_up_down_ratio = float('inf') if entity_up > 0 else 0.0
    
    # 构建结果
    result = pd.DataFrame([{
        'time': df_now['time'].iloc[0] if 'time' in df_now.columns else '',
        'entity_up': int(entity_up),
        'entity_down': int(entity_down),
        'entity_flat': int(entity_flat),
        'entity_total': total,
        'entity_up_ratio': entity_up_ratio,
        'entity_down_ratio': entity_down_ratio,
        'entity_flat_ratio': entity_flat_ratio,
        'entity_up_down_ratio': entity_up_down_ratio,
    }])
    
    return result

# 在 deal_zq_works 中调用
bond_stats = calculate_bond_market_stats(df_now)
if not bond_stats.empty:
    bond_stats_table = f"monitor_zq_stats_{date_str}"
    save_dataframe_async(bond_stats, bond_stats_table, time_full, EXPIRE_SECONDS)
```

---

## 数据库表结构更新

### 股票大盘统计表（monitor_gp_apqd_YYYYMMDD）

```sql
-- 新增字段
ALTER TABLE monitor_gp_apqd_20260513 
ADD COLUMN entity_up INT DEFAULT 0 COMMENT '实体上涨数量',
ADD COLUMN entity_down INT DEFAULT 0 COMMENT '实体下跌数量',
ADD COLUMN entity_flat INT DEFAULT 0 COMMENT '实体平盘数量',
ADD COLUMN entity_up_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体上涨占比(%)',
ADD COLUMN entity_down_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体下跌占比(%)',
ADD COLUMN entity_flat_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体平盘占比(%)',
ADD COLUMN entity_up_down_ratio DECIMAL(8,2) DEFAULT 0 COMMENT '实体上涨下跌比';
```

### 债券大盘统计表（新增 monitor_zq_stats_YYYYMMDD）

```sql
CREATE TABLE IF NOT EXISTS monitor_zq_stats_20260513 (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    time TIME NOT NULL COMMENT '时间',
    entity_up INT DEFAULT 0 COMMENT '实体上涨数量',
    entity_down INT DEFAULT 0 COMMENT '实体下跌数量',
    entity_flat INT DEFAULT 0 COMMENT '实体平盘数量',
    entity_total INT DEFAULT 0 COMMENT '总数量',
    entity_up_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体上涨占比(%)',
    entity_down_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体下跌占比(%)',
    entity_flat_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '实体平盘占比(%)',
    entity_up_down_ratio DECIMAL(8,2) DEFAULT 0 COMMENT '实体上涨下跌比',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_time (time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='债券大盘统计表';
```

---

## 前端展示设计

### 大盘概览卡片（monitor.html）

```html
<!-- 股票大盘概览 -->
<div class="market-section">
    <h2>
        <span>📈 股票市场</span>
        <span class="auction-badge" id="stock-auction-badge" style="display:none">集合竞价</span>
    </h2>
    <div class="market-dual">
        <div class="market-type-header">A股市场</div>
        <div class="market-grid" id="stock-market-grid">
            <!-- 【新增】实体上涨下跌比 -->
            <div class="market-item">
                <div class="market-label">涨跌比</div>
                <div class="market-value" id="stock-entity-up-down-ratio">-</div>
                <div class="market-sub">实体上涨/下跌</div>
            </div>
            <div class="market-item">
                <div class="market-label">上涨家数</div>
                <div class="market-value up" id="stock-entity-up">-</div>
                <div class="market-sub" id="stock-entity-up-ratio">-</div>
            </div>
            <div class="market-item">
                <div class="market-label">下跌家数</div>
                <div class="market-value down" id="stock-entity-down">-</div>
                <div class="market-sub" id="stock-entity-down-ratio">-</div>
            </div>
            <!-- 其他字段... -->
        </div>
    </div>
</div>

<!-- 债券大盘概览 -->
<div class="market-section">
    <h2>
        <span>📊 债券市场</span>
    </h2>
    <div class="market-dual">
        <div class="market-type-header">可转债市场</div>
        <div class="market-grid" id="bond-market-grid">
            <!-- 【新增】实体上涨下跌比 -->
            <div class="market-item">
                <div class="market-label">涨跌比</div>
                <div class="market-value" id="bond-entity-up-down-ratio">-</div>
                <div class="market-sub">实体上涨/下跌</div>
            </div>
            <div class="market-item">
                <div class="market-label">上涨家数</div>
                <div class="market-value up" id="bond-entity-up">-</div>
                <div class="market-sub" id="bond-entity-up-ratio">-</div>
            </div>
            <div class="market-item">
                <div class="market-label">下跌家数</div>
                <div class="market-value down" id="bond-entity-down">-</div>
                <div class="market-sub" id="bond-entity-down-ratio">-</div>
            </div>
            <!-- 其他字段... -->
        </div>
    </div>
</div>
```

### 前端 JavaScript 更新

```javascript
// 更新股票大盘数据
function updateStockMarketStats(data) {
    // 【新增】实体上涨下跌比
    const entityUpDownRatio = data.entity_up_down_ratio || 0;
    const entityUp = data.entity_up || 0;
    const entityDown = data.entity_down || 0;
    const entityUpRatio = data.entity_up_ratio || 0;
    const entityDownRatio = data.entity_down_ratio || 0;
    
    // 格式化显示
    let ratioText = '-';
    let ratioClass = 'neutral';
    
    if (entityUpDownRatio === Infinity) {
        ratioText = '∞';  // 无下跌，全部上涨
        ratioClass = 'up';
    } else if (entityUpDownRatio > 0) {
        ratioText = entityUpDownRatio.toFixed(2);
        if (entityUpDownRatio > 1.5) {
            ratioClass = 'up';  // 明显多头
        } else if (entityUpDownRatio < 0.67) {
            ratioClass = 'down';  // 明显空头
        } else {
            ratioClass = 'neutral';  // 平衡
        }
    }
    
    // 更新DOM
    const ratioEl = document.getElementById('stock-entity-up-down-ratio');
    ratioEl.textContent = ratioText;
    ratioEl.className = `market-value ${ratioClass}`;
    
    document.getElementById('stock-entity-up').textContent = entityUp;
    document.getElementById('stock-entity-up-ratio').textContent = `占比 ${entityUpRatio.toFixed(1)}%`;
    
    document.getElementById('stock-entity-down').textContent = entityDown;
    document.getElementById('stock-entity-down-ratio').textContent = `占比 ${entityDownRatio.toFixed(1)}%`;
}

// 更新债券大盘数据（类似）
function updateBondMarketStats(data) {
    // ... 同上逻辑 ...
}
```

---

## 解读指南

### 涨跌比数值含义

| 涨跌比 | 市场状态 | 操作建议 |
|--------|----------|----------|
| ∞ | 全部上涨，无下跌 | 极强多头，注意回调风险 |
| > 3.0 | 上涨远多于下跌 | 强势市场，积极做多 |
| 1.5 - 3.0 | 上涨明显多于下跌 | 偏多市场，谨慎做多 |
| 0.67 - 1.5 | 涨跌平衡 | 震荡市场，观望为主 |
| 0.33 - 0.67 | 下跌明显多于上涨 | 偏空市场，谨慎做空 |
| < 0.33 | 下跌远多于上涨 | 弱势市场，积极做空 |
| 0 | 无上涨，全部下跌 | 极弱空头，注意反弹 |

### 结合其他指标

```
涨跌比 + 大盘强度评分:
- 涨跌比 > 2.0 + 强度评分 > 80: 强势上涨，可追涨
- 涨跌比 < 0.5 + 强度评分 < 20: 强势下跌，可止损
- 涨跌比 ≈ 1.0 + 强度评分 40-60: 震荡市，高抛低吸
```

---

## 实施步骤

### 步骤1：后端修改

1. 修改 `monitor_stock.py`:
   - 更新 `get_market_stats_v2` 函数，增加实体统计计算
   - 更新 `judge_market_strength` 函数，使用新字段

2. 修改 `monitor_bond.py`:
   - 新增 `calculate_bond_market_stats` 函数
   - 在 `deal_zq_works` 中调用

### 步骤2：数据库更新

1. 修改大盘强度表结构，增加实体统计字段
2. 新增债券大盘统计表

### 步骤3：前端修改

1. 更新 `monitor.html`，增加涨跌比展示
2. 更新 JavaScript，处理新字段

### 步骤4：测试验证

1. 验证股票涨跌比计算正确
2. 验证债券涨跌比计算正确
3. 验证前端展示正常
4. 验证历史数据兼容性

---

## 总结

| 项目 | 内容 |
|------|------|
| **新增字段** | `entity_up_down_ratio` - 实体上涨下跌比 |
| **计算公式** | `entity_up_count / entity_down_count` |
| **股票位置** | `monitor_stock.py` - `get_market_stats_v2` |
| **债券位置** | `monitor_bond.py` - 新增 `calculate_bond_market_stats` |
| **前端位置** | `monitor.html` - 大盘概览卡片 |
| **数据库** | 股票表增加字段，债券表新增 |

---

*设计方案完成*