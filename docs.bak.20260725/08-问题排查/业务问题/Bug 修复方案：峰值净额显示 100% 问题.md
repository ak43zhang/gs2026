# Bug 修复方案：峰值净额显示 100% 问题

## 文档信息

- **版本**: v1.0
- **日期**: 2026-05-13
- **Bug 编号**: BUG-2026-001
- **严重级别**: 中
- **影响范围**: 股票排行页面 - 峰值净额列

---

## 一、问题概述

### 1.1 现象描述

以股票 `301396` 为例：
- 前端显示"主力资金": -248.1万（实际是当前累计值）
- 峰值净额: 66.1万
- 回落百分比: **100%** ← 错误！

**预期结果**: 应该显示实际的回落百分比（可能是 475%+，表示资金大幅流出）

**实际结果**: 始终显示 100%（当峰值存在但当前值获取失败时）

### 1.2 影响范围

- 所有股票排行页面的"峰值净额"列
- 影响用户对主力资金流向的判断
- 可能导致错误的投资决策

---

## 二、根因分析

### 2.1 问题定位

**后端代码** (`src/gs2026/dashboard2/routes/monitor.py` 第 417-418 行):
```python
# 主力净额（已从cumulative_main_net或main_net_amount获取）
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
# ❌ 缺少: stock['cumulative_main_net'] = main_net
```

**前端代码** (`src/gs2026/dashboard2/templates/monitor.html` 第 1350 行):
```javascript
case 'max_cumulative_main_net': {
    const current = item.cumulative_main_net || 0;  // ❌ 实际为 undefined
    const peak = item.max_cumulative_main_net || 0;  // ✓ 66.1万
    
    // 计算回落百分比
    const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
    // 结果: (661000 - 0) / 661000 * 100 = 100%
```

### 2.2 问题本质

**字段名不匹配**:
- 后端赋值给 `main_net_amount`
- 前端读取 `cumulative_main_net`
- 两者实际上是同一个数据（累计主力净额）

**计算结果错误**:
- 当 `current = 0`（因为字段不存在）
- 当 `peak = 66.1万`
- `dropPct = (66.1 - 0) / 66.1 × 100 = 100%`

---

## 三、修复方案

### 方案一：后端添加字段（推荐）⭐

**修改文件**: `src/gs2026/dashboard2/routes/monitor.py`

**修改位置**: 第 417-418 行后

**修改内容**:
```python
# 填充数据
for stock in stocks:
    code = stock.get('code', '').zfill(6)
    
    # 涨跌幅（当前时间点）
    change_pct = change_pct_map.get(code)
    stock['change_pct'] = change_pct if change_pct is not None else '-'
    
    # 主力净额（已从cumulative_main_net或main_net_amount获取）
    main_net = main_net_map.get(code)
    stock['main_net_amount'] = main_net if main_net is not None else 0
    stock['cumulative_main_net'] = main_net if main_net is not None else 0  # ⭐ 新增
    
    # 派生字段（自动填充）
    for fname, fmap in derived_maps.items():
        stock[fname] = fmap.get(code, 0)
```

**优点**:
1. 保持字段语义清晰（`main_net_amount` 用于显示，`cumulative_main_net` 用于计算）
2. 前端代码无需修改
3. 符合代码可读性原则
4. 未来如果需要区分显示值和计算值，结构清晰

**缺点**:
1. 增加少量数据传输（重复字段）

---

### 方案二：前端修改字段名

**修改文件**: `src/gs2026/dashboard2/templates/monitor.html`

**修改位置**: 第 1350 行

**修改内容**:
```javascript
case 'max_cumulative_main_net': {
    const current = item.main_net_amount || 0;  // ⭐ 改为使用 main_net_amount
    const peak = item.max_cumulative_main_net || 0;
    
    if (peak === 0) return '<td>-</td>';
    
    // 计算回落百分比
    const dropPct = peak > 0 ? ((peak - current) / peak * 100).toFixed(1) : 0;
    // ...
}
```

**优点**:
1. 后端无需修改
2. 减少数据传输

**缺点**:
1. 字段名语义不清晰（`main_net_amount` 实际存储的是累计值）
2. 如果未来需要区分单时段和累计值，会产生混淆
3. 前端与后端字段名紧耦合

---

### 方案三：统一字段名（重构）

**修改范围**: 前后端同时修改

**修改内容**:
1. 后端统一使用 `cumulative_main_net` 作为字段名
2. 前端适配新字段名
3. 废弃 `main_net_amount` 字段（或作为别名保留）

**优点**:
1. 字段名语义清晰
2. 代码可维护性高

**缺点**:
1. 修改范围大
2. 需要测试所有使用到该字段的地方
3. 风险较高

---

## 四、推荐方案

**推荐采用方案一：后端添加字段**

**理由**:
1. **风险最低**: 只修改后端一行代码，前端无需改动
2. **语义清晰**: 两个字段分别用于不同目的
3. **兼容性好**: 不影响现有功能
4. **易于回滚**: 如果出现问题，可以快速回滚

---

## 五、实施步骤

### 5.1 代码修改

```bash
# 1. 备份原文件
cp src/gs2026/dashboard2/routes/monitor.py src/gs2026/dashboard2/routes/monitor.py.bak

# 2. 修改代码（在 417-418 行后添加一行）
# stock['cumulative_main_net'] = main_net if main_net is not None else 0

# 3. 验证修改
grep -n "cumulative_main_net" src/gs2026/dashboard2/routes/monitor.py
```

### 5.2 测试验证

**测试用例 1**: 正常情况
```
股票: 301396
- 主力资金: -248.1万
- 峰值净额: 66.1万
- 预期回落: 475.2%
```

**测试用例 2**: 峰值等于当前值
```
股票: 某强势股票
- 主力资金: 100万
- 峰值净额: 100万
- 预期回落: 0%
```

**测试用例 3**: 当前值为0
```
股票: 某无资金股票
- 主力资金: 0
- 峰值净额: 50万
- 预期回落: 100%
```

**测试用例 4**: 峰值为0
```
股票: 某无峰值股票
- 主力资金: 0
- 峰值净额: 0
- 预期显示: "-"
```

### 5.3 部署流程

1. **开发环境验证**
   - 本地启动服务
   - 访问股票排行页面
   - 验证峰值净额列显示正确

2. **测试环境部署**
   - 部署到测试服务器
   - 运行自动化测试
   - 人工验证关键场景

3. **生产环境部署**
   - 选择交易低峰期（如午休时间）
   - 灰度发布（先部署一台服务器）
   - 监控错误日志
   - 全量发布

---

## 六、验证清单

### 6.1 功能验证

- [ ] 峰值净额列显示正确的百分比
- [ ] 回落超过20%显示红色警告样式
- [ ] 保持在95%以上显示绿色强势样式
- [ ] 峰值为0时显示 "-"
- [ ] 排序功能正常
- [ ] 时间轴切换时数据更新正确

### 6.2 兼容性验证

- [ ] 其他列显示正常
- [ ] 债券排行页面不受影响
- [ ] 行业排行页面不受影响
- [ ] 移动端显示正常（如果适用）

### 6.3 性能验证

- [ ] 页面加载时间无明显增加
- [ ] API 响应时间无明显增加
- [ ] 内存使用无明显增加

---

## 七、回滚方案

### 7.1 回滚条件

- 修复后出现新的错误
- 性能明显下降
- 用户反馈异常

### 7.2 回滚步骤

```bash
# 1. 停止服务
sudo systemctl stop dashboard2

# 2. 恢复备份
cp src/gs2026/dashboard2/routes/monitor.py.bak src/gs2026/dashboard2/routes/monitor.py

# 3. 重启服务
sudo systemctl start dashboard2

# 4. 验证回滚
curl http://localhost:5000/monitor/attack-ranking/stock
```

### 7.3 回滚验证

- [ ] 服务正常启动
- [ ] 股票排行页面可访问
- [ ] 峰值净额列显示 100%（回到修复前状态）

---

## 八、相关代码片段

### 8.1 修改前代码

```python
# monitor.py 第 410-420 行
        # 填充数据
        for stock in stocks:
            code = stock.get('code', '').zfill(6)
            
            # 涨跌幅（当前时间点）
            change_pct = change_pct_map.get(code)
            stock['change_pct'] = change_pct if change_pct is not None else '-'
            
            # 主力净额（已从cumulative_main_net或main_net_amount获取）
            main_net = main_net_map.get(code)
            stock['main_net_amount'] = main_net if main_net is not None else 0
            
            # 派生字段（自动填充）
            for fname, fmap in derived_maps.items():
                stock[fname] = fmap.get(code, 0)
```

### 8.2 修改后代码

```python
# monitor.py 第 410-422 行
        # 填充数据
        for stock in stocks:
            code = stock.get('code', '').zfill(6)
            
            # 涨跌幅（当前时间点）
            change_pct = change_pct_map.get(code)
            stock['change_pct'] = change_pct if change_pct is not None else '-'
            
            # 主力净额（已从cumulative_main_net或main_net_amount获取）
            main_net = main_net_map.get(code)
            stock['main_net_amount'] = main_net if main_net is not None else 0
            stock['cumulative_main_net'] = main_net if main_net is not None else 0  # ⭐ 新增
            
            # 派生字段（自动填充）
            for fname, fmap in derived_maps.items():
                stock[fname] = fmap.get(code, 0)
```

---

## 九、附录

### 9.1 相关文档

- [字段规范文档](./fields-specification.md)
- [计算逻辑文档](./calculation-logic.md)
- [数据库表结构](./database-schema.md)

### 9.2 相关文件

| 文件路径 | 说明 |
|----------|------|
| `src/gs2026/dashboard2/routes/monitor.py` | 后端API路由（需修改） |
| `src/gs2026/dashboard2/templates/monitor.html` | 前端模板（无需修改） |
| `src/gs2026/monitor/monitor_stock.py` | 数据计算脚本（参考） |

### 9.3 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-05-13 | 初始版本 |

---

*文档结束*