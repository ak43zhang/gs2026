# Bug 修复记录

## 修复信息

- **Bug 编号**: BUG-2026-001
- **修复日期**: 2026-05-13
- **修复人**: AI Assistant
- **状态**: ✅ 已修复

---

## 问题描述

**现象**: 股票排行页面"峰值净额"列始终显示 100% 回落

**影响**: 以股票 301396 为例
- 主力资金: -248.1万
- 峰值净额: 66.1万  
- 错误显示: 100%
- 正确应为: 475.2%（表示资金大幅流出）

---

## 根因分析

**后端代码** (`monitor.py` 第 417-418 行):
```python
main_net = main_net_map.get(code)
stock['main_net_amount'] = main_net if main_net is not None else 0
# ❌ 缺少 stock['cumulative_main_net'] 赋值
```

**前端代码** (`monitor.html` 第 1350 行):
```javascript
const current = item.cumulative_main_net || 0;  // 实际为 undefined
const peak = item.max_cumulative_main_net || 0;  // 66.1万

// 计算: (661000 - 0) / 661000 * 100 = 100%
```

**结论**: 后端赋值给 `main_net_amount`，但前端读取 `cumulative_main_net`，字段名不匹配导致 `current = 0`。

---

## 修复方案

**修改文件**: `src/gs2026/dashboard2/routes/monitor.py`

**修改位置**: 第 419 行（在 `main_net_amount` 赋值后）

**修改内容**:
```python
# 修复前
stock['main_net_amount'] = main_net if main_net is not None else 0

# 修复后
stock['main_net_amount'] = main_net if main_net is not None else 0
stock['cumulative_main_net'] = main_net if main_net is not None else 0  # 前端峰值净额计算需要
```

---

## 修复验证

### 代码验证

```bash
# 验证修改已生效
grep -n "cumulative_main_net" src/gs2026/dashboard2/routes/monitor.py
# 输出: 419:stock['cumulative_main_net'] = main_net if main_net is not None else 0
```

### 功能验证（部署后）

**测试用例 1**: 股票 301396
- 主力资金: -248.1万
- 峰值净额: 66.1万
- 预期回落: 475.2%（红色警告 ↓）

**测试用例 2**: 强势股票
- 主力资金: 100万
- 峰值净额: 100万
- 预期回落: 0%（绿色强势 →）

**测试用例 3**: 无资金股票
- 主力资金: 0
- 峰值净额: 0
- 预期显示: "-"

---

## 部署步骤

1. **提交代码**
   ```bash
   git add src/gs2026/dashboard2/routes/monitor.py
   git commit -m "Fix: 峰值净额列显示100%问题 - 添加cumulative_main_net字段"
   ```

2. **部署到测试环境**
   ```bash
   git push origin main
   # 触发CI/CD部署
   ```

3. **验证修复**
   - 访问股票排行页面
   - 检查峰值净额列显示
   - 确认百分比计算正确

4. **部署到生产环境**
   - 选择交易低峰期
   - 灰度发布
   - 监控日志

---

## 回滚方案

如需回滚:
```bash
# 恢复备份
cp src/gs2026/dashboard2/routes/monitor.py.bak src/gs2026/dashboard2/routes/monitor.py

# 重启服务
sudo systemctl restart dashboard2
```

---

## 相关文档

- [Bug 修复方案](./bug-fix-peak-percentage.md)
- [字段规范文档](./fields-specification.md)
- [计算逻辑文档](./calculation-logic.md)

---

*修复完成*
