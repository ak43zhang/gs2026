# 大盘阶段检测方案

> 通过大盘实时数据判断当前处于：上升 / 下降 / 反弹 / 回落 / 震荡

---

## 一、已有数据源

### 数据表

| 表名 | 说明 | 每tick行数 | 每天行数 |
|------|------|-----------|---------|
| `monitor_gp_apqd_{date}` | 股票大盘强度汇总 | 1 | ~4,710 |
| `monitor_zq_apqd_{date}` | 债券大盘强度汇总 | 1 | ~4,710 |

### 关键字段

| 字段 | 含义 | 示例 |
|------|------|------|
| `time` | tick 时间 | `14:56:54` |
| `body_up` | 红实体柱家数 | 1520 |
| `body_down` | 绿实体柱家数 | 3487 |
| `min_up` | 相对上一分钟上涨家数 | 2032 |
| `min_down` | 相对上一分钟下跌家数 | 1446 |

> tick 频率：3秒/次

---

## 二、核心算法

### 双窗口对比

```
近期窗口（前60tick ≈ 3分钟）  → 红柱占比、tick上涨占比
参照窗口（第61~160tick ≈ 前5分钟）  → 作为对比基准
```

### 动量计算

```python
momentum = (近期红柱占比 - 参照红柱占比) × 0.6
         + (近期tick占比 - 参照tick占比) × 0.4
```

### 阶段判定矩阵

| 当前状态 | 趋势方向 | 阶段 | 颜色 |
|----------|----------|------|------|
| 多方占优（body > 0.5） | 改善（momentum > 0） | 🔴 上升（rising） | 红 |
| 多方占优（body > 0.5） | 恶化（momentum < 0） | 🟡 回落（pullback） | 黄 |
| 空方占优（body < 0.5） | 改善（momentum > 0） | 🟢 反弹（rebound） | 绿 |
| 空方占优（body < 0.5） | 恶化（momentum < 0） | ⚫ 下降（falling） | 灰 |
| 动量极小（\|momentum\| < 0.005） | — | ➡️ 震荡（neutral） | 蓝 |

### 强度分级

| 动量绝对值 | 强度 |
|-----------|------|
| > 0.05 | 强（strong） |
| > 0.02 | 中（medium） |
| ≤ 0.02 | 弱（weak） |

---

## 三、性能验证

| 方案 | 平均耗时 | 备注 |
|------|----------|------|
| 方案1：取160行 + Python计算 | **15.6ms** ✅ | SELECT 简单，Python 简单求均值 |
| 方案2：纯 SQL 子查询 | 41.9ms | 4个嵌套子查询 |
| 方案3：窗口函数 ROW_NUMBER | 28.9ms | 扫描全表再分配序号 |

**推荐方案1**：对 `apqd` 小表（~5MB，4710行），`ORDER BY time DESC LIMIT 160` 利用 `time` 列 BTREE 索引，耗时最低。

---

## 四、数据流

```
监控循环(每3秒)
  │
  ├─ get_market_stats_v2() → 计算 body_up/body_down/min_up/min_down 等
  ├─ judge_market_strength() → 计算 strength_score/state/signal
  ├─ _compute_phase_for_tick() → 读前159tick + 当前tick数据 → 计算阶段 [新增]
  ├─ 写入 judge30 DataFrame（含 market_phase/phase_strength/phase_momentum）
  └─ save_dataframe_async() → 存入 monitor_{gp|zq}_apqd_{date}
         │
         ▼
API: get_market_overview()
  ├─ data_service.get_market_stats() → 读 apqd 表最新行 → to_dict()
  └─ 自动包含 market_phase/phase_strength/phase_momentum [零改动]
         │
         ▼
前端: renderMarketData()
  └─ 读 data.market_phase → 显示彩色标签
```

---

## 五、存储设计

### 新增字段（存入 apqd 表）

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| `market_phase` | VARCHAR(10) | 阶段英文标识 | `rising` |
| `phase_strength` | VARCHAR(10) | 强度英文标识 | `strong` |
| `phase_momentum` | DECIMAL(10,6) | 动量值 | `0.035000` |

### 写入时机

在 `culculate_gp_apqd_top30()` 中，`judge30` DataFrame 构建后、`save_dataframe_async()` 前，追加3列。

### 边界处理

| 场景 | 处理 |
|------|------|
| 表不存在（开盘前首次写入） | 返回 neutral/weak/0 |
| 数据不足20条 | 返回 neutral/weak/0 |
| 参照窗口为空（数据不足60条） | 近期窗口 = 参照窗口，momentum ≈ 0 |
| 计算异常 | catch 异常，写入默认值，记录 warning 日志 |

---

## 六、前端展示

### 显示位置

在监控页面大盘概览卡片的标题右侧：

```
📊 股票大盘  📈 上升(强)
```

### CSS 样式

```css
.market-phase {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    margin-left: 8px;
}
.phase-rising   { background: #ffebee; color: #e53935; }
.phase-pullback { background: #fff8e1; color: #f9a825; }
.phase-rebound  { background: #e8f5e9; color: #43a047; }
.phase-falling  { background: #f5f5f5; color: #616161; }
.phase-neutral  { background: #e3f2fd; color: #1565c0; }
```

---

## 七、文件改动汇总

| 文件 | 改动 | 行数 |
|------|------|------|
| `monitor_stock.py` | 新增 `_compute_phase_for_tick()` | +40行 |
| `monitor_stock.py` | 修改 `culculate_gp_apqd_top30()` 追加阶段列 | +8行 |
| `monitor_bond.py` | 同样的阶段计算调用 | +8行 |
| `monitor.html` | CSS + HTML + JS 渲染阶段标签 | +20行 |
| **总计** | | **~76行** |

> `monitor.py` 的 `get_market_overview()` **无需修改**——`data_service.get_market_stats()` 通过 `row.to_dict()` 自动返回新增字段。

---

## 八、后续可扩展

| 扩展方向 | 说明 |
|----------|------|
| 阶段切换预警 | 当阶段从 A 变为 B 时，前端弹出提示 |
| 阶段持久化到独立表 | 如需长期历史阶段查询，可建立 `market_phase_{date}` 表 |
| 权重参数调优 | `0.6/0.4` 红柱/tick 权重可随市场验证调整 |
| 窗口大小配置化 | 近期窗口和参照窗口的 tick 数量可做成配置项 |
