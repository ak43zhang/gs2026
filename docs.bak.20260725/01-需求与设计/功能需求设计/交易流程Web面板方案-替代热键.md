# 交易流程管理 - Web面板方案设计

> 版本: v2.0 (替代热键方案)
> 日期: 2026-07-16
> 状态: 待审核

---

## 一、需求变更

### 1.1 原方案问题

| 问题 | 说明 |
|------|------|
| 热键冲突 | Ctrl+Shift+Y 与其他软件冲突,无法使用 |
| 不直观 | 看不到当前有多少待处理订单 |
| 无撤单 | 买入后未成交无法自动撤销 |
| 操作盲 | 不清楚系统当前在做什么 |

### 1.2 新需求

1. **Web面板替代热键** — 浏览器页面实时显示所有待处理订单
2. **一键确认** — 在面板上点击确认/跳过
3. **自动撤单** — 买入后30秒未成交,自动撤销委托
4. **快速流程** — 点买入后立刻回面板操作,尽量少切换窗口

---

## 二、优化后的交易流程

### 2.1 完整时间线

```
[10:30:03] 量化命中
    → 计算买入价 = 105.0 + 0.3 = 105.3
    → 填充xiadan.exe买入表单(自动)
    → Web面板出现新订单卡片: "127045 某转债 @105.3 等待买入"
    → 状态: WAIT_BUY

[10:30:05] 你在xiadan.exe点击[买入]
    → 回到Web面板
    → 点击[已买入]按钮
    → 状态: CONFIRMING (开始30秒倒计时)
    → 面板显示: "等待成交确认... 28秒"

[分支A: 成交了]
[10:30:08] 可转债秒成交(正常情况)
    → 面板上点[确认成交 → 设置止盈止损]
    → 系统自动: 打开条件单 → 填充TP/SL → 提交
    → 状态: TP_SL_SET ✓

[分支B: 未成交,手动撤]
[10:30:15] 你发现没成交
    → 面板上点[撤单]
    → 系统自动: 在xiadan.exe执行撤单操作
    → 状态: CANCELLED

[分支C: 超时自动撤]
[10:31:05] 30秒未确认
    → 系统自动: 执行撤单
    → 面板显示: "超时自动撤单"
    → 状态: TIMEOUT_CANCELLED
    → 处理队列中下一个
```

### 2.2 与原方案对比

| | 原方案(热键) | 新方案(Web面板) |
|---|---|---|
| 确认方式 | Ctrl+Shift+Y | 面板点击按钮 |
| 信息展示 | 无(盲操作) | 实时面板,所有订单一目了然 |
| 撤单 | 不支持 | 30秒超时自动撤 + 手动撤 |
| 窗口切换 | 华泰→按键 | 华泰→浏览器(可并排) |
| 多订单 | 看不到队列 | 队列可视化 |

---

## 三、Web面板设计

### 3.1 面板布局

```
┌────────────────────────────────────────────────────────┐
│  ⚡ 交易助手面板         实时刷新: 1秒    队列: 2      │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │ 📌 当前订单                                   │     │
│  │                                              │     │
│  │  127045 某某转债                              │     │
│  │  买入价: 105.300  状态: 等待成交确认           │     │
│  │  止盈: 3%  止损: 2%  数量: 10股               │     │
│  │  倒计时: 25秒                                 │     │
│  │                                              │     │
│  │  [✓ 确认成交,设置止盈止损]  [✗ 撤单]         │     │
│  │                                              │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │ 📋 等待队列 (2个)                             │     │
│  │                                              │     │
│  │  1. 128015 另一转债 @110.2 TP:3% SL:2%       │     │
│  │  2. 123456 第三转债 @98.5  TP:5% SL:3%       │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
│  ┌──────────────────────────────────────────────┐     │
│  │ 📜 今日记录                                   │     │
│  │                                              │     │
│  │  10:25 127001 成功转债 TP_SL_SET ✓           │     │
│  │  10:20 127002 超时转债 TIMEOUT_CANCELLED      │     │
│  └──────────────────────────────────────────────┘     │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 3.2 面板端点

复用现有 HuaTaiTrader HTTP服务(8081端口):

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /panel` | GET | 面板HTML页面 |
| `GET /api/trade/status` | GET | 当前订单+队列+历史(JSON) |
| `POST /api/trade/bought` | POST | 用户点了买入(开始倒计时) |
| `POST /api/trade/confirm` | POST | 确认成交 → 触发止盈止损 |
| `POST /api/trade/cancel` | POST | 撤单(手动) |
| `POST /api/trade/skip` | POST | 跳过当前 |

### 3.3 页面技术

- 纯HTML + JS, 无需框架
- 每秒fetch `/api/trade/status` 刷新状态
- 倒计时用JS本地计算(减少请求)
- 按钮点击调用对应API

---

## 四、订单状态机(修订版)

```
CREATED ──→ WAIT_BUY ──→ CONFIRMING ──→ FILLED ──→ TP_SL_SET
               │              │             │
               │              │             └──→ TP_SL_FAILED
               │              │
               │              ├──→ TIMEOUT_CANCELLED (30秒超时,自动撤单)
               │              │
               │              └──→ CANCELLED (手动撤单)
               │
               └──→ SKIPPED (手动跳过)
```

**状态说明:**

| 状态 | 含义 | 面板显示 | 可用操作 |
|------|------|---------|---------|
| WAIT_BUY | 买入表单已填充,等待你点买入 | "请在华泰点击买入" | [已买入] [跳过] |
| CONFIRMING | 你说已点买入,等待成交确认 | "等待成交... 25秒" | [确认成交] [撤单] |
| FILLED | 已确认成交,正在设置止盈止损 | "设置止盈止损中..." | 无(自动) |
| TP_SL_SET | 条件单已提交 ✓ | "完成 ✓" | - |
| TIMEOUT_CANCELLED | 超时自动撤单 | "超时撤单" | - |
| CANCELLED | 手动撤单 | "已撤单" | - |

---

## 五、两步确认流程(核心优化)

### 5.1 为何分"已买入"和"确认成交"两步?

```
面板操作:
  [已买入] ← 你在华泰点了买入按钮(此时可能还没成交)
       │
       │ 开始30秒倒计时
       │ 系统可以在这个时间段检查是否成交
       │
       ▼
  [确认成交] ← 你确认确实成交了(看到当日成交记录)
       │
       ▼
  自动设置止盈止损
```

**但如果觉得两步太繁琐,也可以简化为一步:**

### 5.2 简化版(推荐): 一步确认

```
面板操作:
  [买入并设置止盈止损] ← 点击后: 系统认为已买入+已成交, 直接设置TP/SL
  [跳过] ← 不买
  
  自动逻辑:
  - 如果30秒内没点任何按钮 → 自动撤单
```

**一步版流程:**
1. 系统填充买入表单 → 面板显示订单卡片
2. 你在华泰点买入
3. 回面板点[确认 → 设置止盈止损] (一个按钮搞定)
4. 系统自动提交条件单

### 5.3 建议采用: 一步确认 + 自动撤单兜底

| 场景 | 处理 |
|------|------|
| 正常: 买入成交了 | 点[确认] → 设TP/SL |
| 异常: 买了但没成交 | 30秒超时 → 自动撤单 |
| 放弃: 不想买 | 点[跳过] 或 等超时 |

---

## 六、自动撤单设计

### 6.1 撤单操作方式

xiadan.exe中撤单的操作路径:
- F3 切换到撤单面板
- 在撤单列表中找到对应委托
- 双击或选中后点撤单

**自动化实现:** 与买入填充相同方式(HTTP API → HuaTaiTrader)

```python
# 调用现有HuaTaiTrader的撤单接口
POST /api/cancel_order
{
    "code": "127045",     # 证券代码
    "direction": "buy"    # 买入委托
}
```

### 6.2 撤单时机

```python
# 超时撤单逻辑(在每秒轮询中检查)
if order.status == "CONFIRMING":
    elapsed = now - order.bought_at
    if elapsed >= 30:
        # 1. 调用撤单API
        cancel_result = trader.cancel_order(order.bond_code)
        # 2. 更新状态
        order.status = "TIMEOUT_CANCELLED"
        # 3. 处理下一个
        pipeline.process_next()
```

### 6.3 撤单失败处理

| 情况 | 处理 |
|------|------|
| 已成交(无法撤) | 说明已买入,面板提示"已成交,请确认" |
| 撤单成功 | 标记CANCELLED,处理下一个 |
| 撤单失败(其他原因) | 告警,保持CONFIRMING让用户手动处理 |

---

## 七、monitor_bond.py 集成接口(不变)

```python
# monitor_bond.py 中的调用方式不变:
from trade_flow import get_trade_flow_manager

manager = get_trade_flow_manager()

# 命中时:
manager.on_hit(bond_code, bond_name, hit_price, scheme_detail, lots)

# 每tick:
manager.check_timeout()  # 检查超时撤单

# Web面板的按钮操作通过HTTP API触发:
# POST /api/trade/confirm → manager.on_confirm()
# POST /api/trade/cancel  → manager.on_cancel()
# POST /api/trade/skip    → manager.on_skip()
```

---

## 八、技术实现要点

### 8.1 前端(面板HTML)

```javascript
// 核心: 每秒刷新
setInterval(async () => {
    const resp = await fetch('/api/trade/status');
    const data = await resp.json();
    renderPanel(data);
    updateCountdown(data.current);
}, 1000);

// 按钮点击
async function onConfirm() {
    await fetch('/api/trade/confirm', {method: 'POST'});
}
async function onCancel() {
    await fetch('/api/trade/cancel', {method: 'POST'});
}
```

### 8.2 后端(Flask路由)

```python
@app.route('/api/trade/status')
def trade_status():
    return jsonify(manager.get_status())

@app.route('/api/trade/confirm', methods=['POST'])
def trade_confirm():
    manager.on_confirm()
    return jsonify({'success': True})

@app.route('/api/trade/cancel', methods=['POST'])
def trade_cancel():
    manager.on_cancel()  # 执行撤单 + 更新状态
    return jsonify({'success': True})
```

### 8.3 自动撤单(后台线程)

```python
def _timeout_checker():
    """每秒检查一次超时"""
    while True:
        order = pipeline.current
        if order and order.status == "CONFIRMING":
            elapsed = (now() - order.bought_at).total_seconds()
            if elapsed >= 30:
                # 执行撤单
                trader.cancel_order(order.bond_code)
                order.status = "TIMEOUT_CANCELLED"
                pipeline.process_next()
        time.sleep(1)
```

---

## 九、操作流程总结(用户视角)

```
你的日常操作(只需两个窗口):

┌─ 华泰xiadan.exe ─┐    ┌─ 浏览器: localhost:8081/panel ─┐
│                    │    │                                 │
│  [命中时自动弹出    │    │  ⚡ 当前: 127045 某转债 @105.3  │
│   买入表单]        │    │     止盈3% 止损2% 10股          │
│                    │    │     [确认→设止盈止损] [跳过]    │
│  你看一眼价格      │    │                                 │
│  → 点[买入]       │    │  📋 队列: 2个等待               │
│  → 切到浏览器     │    │  📜 今日: 3单完成               │
│                    │    │                                 │
└────────────────────┘    └─────────────────────────────────┘

操作顺序:
1. 看到华泰弹出买入表单 → 点买入(1秒)
2. 切到浏览器面板 → 点确认(1秒)
3. 系统自动设置止盈止损(3秒)
4. 完成! 处理下一个
```

**总耗时: ~5秒/单(你的操作只有2次点击)**

---

## 十、实施计划

| 步骤 | 内容 | 工作量 |
|------|------|--------|
| 1 | trade_flow.py 核心逻辑(已写好框架) | 完善 |
| 2 | 面板HTML页面(panel.html) | 新建 |
| 3 | Flask API路由 | 在server.py中新增 |
| 4 | 自动撤单功能 | 新增cancel_order接口 |
| 5 | 集成测试(test_full_flow.py) | 完善 |
| 6 | 接入monitor_bond.py | 改动极小 |

---

## 十一、已确认决策

| # | 问题 | 确定结果 |
|---|------|---------|
| 1 | 确认方式 | **一步确认**(点买入后回面板直接确认) |
| 2 | 面板端口 | **复用8081** |
| 3 | 撤单超时 | **30秒未买进自动撤单** |
| 4 | 面板密码 | **不要** |
| 5 | 盈亏统计 | **本版不做**(后续迭代) |

---

*✅ 方案已确认 — 2026-07-16 18:23*

