# 实时与回溯逻辑同步完善方案

## 目标
实现"修改一处，实时和回溯同时生效"的条件同步机制

---

## 当前状态核查

### ✅ 已同步的条件
- 绿名单条件 `green_bond_in`/`green_bond_out`：前后端都已存在
- 阶段条件 `stock_phase_up`/`bond_phase_up`：前后端都已存在

### ⚠️ 待修复的差异
1. **阶段条件缺 mode='critical'**（后端）
2. **无统一条件定义源**（前端 JS vs 后端 Python 分别维护）

---

## 方案设计

### 方案A：统一 JSON 配置文件（推荐）

**思路**：将 `BP_CONDITIONS` 提取为独立的 JSON 文件，前后端共用

**文件位置**：`F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\config\bp_conditions.json`

**内容结构**：
```json
{
  "version": "2026-05-29",
  "conditions": [
    {
      "id": "body_gt_cur",
      "type": "market",
      "name": "股票红柱>涨家数",
      "on": true,
      "fn_js": "function(m){var s=m.stock||{}; return (parseFloat(s.body_up)||0)>(parseFloat(s.cur_up)||0);}",
      "fn_py": "lambda m, p: float(m.get('stock', {}).get('body_up', 0) or 0) > float(m.get('stock', {}).get('cur_up', 0) or 0)"
    }
  ]
}
```

**优点**：
- 一处修改，前后端自动同步
- 版本控制清晰
- 易于扩展

**缺点**：
- 需要较大重构
- Python lambda 转字符串存储，可读性稍差

---

### 方案B：代码生成器（推荐）

**思路**：维护一个 Python 条件定义文件，生成前端 JS 代码

**文件位置**：
- 源文件：`src/gs2026/dashboard2/config/conditions.py`
- 生成文件：`templates/monitor_conditions.js`

**生成脚本**：`scripts/generate_conditions.py`

**工作流程**：
1. 在 `conditions.py` 中定义所有条件（Python 语法）
2. 运行 `python scripts/generate_conditions.py`
3. 自动生成 `monitor_conditions.js` 供前端使用

**优点**：
- 单源维护（Python）
- 类型安全，可单元测试
- 生成代码可追踪

**缺点**：
- 需要构建步骤
- 复杂条件转换可能丢失细节

---

### 方案C：注释标记同步（轻量）

**思路**：保持现状，但添加强制同步注释和校验脚本

**修改策略**：
1. 前后端文件头部添加同步注释：
   ```python
   # SYNC:BP_CONDITIONS:2026-05-29
   # 前端对应: templates/monitor.html line 2210
   ```
   
   ```javascript
   // SYNC:BP_CONDITIONS:2026-05-29
   // 后端对应: routes/backtest_worker.py line 350
   ```

2. 添加校验脚本 `scripts/check_condition_sync.py`：
   - 解析前后端条件定义
   - 对比 id、type、mode、param、def
   - 不匹配时报错

3. CI/CD 集成：提交前自动运行校验

**优点**：
- 改动最小
- 立即可实施
- 灵活度高

**缺点**：
- 仍需手动维护两处
- 依赖人工执行校验

---

## 推荐方案：C + 渐进式A

### 阶段1（立即实施）：注释标记 + 校验脚本

1. **添加同步注释**到前后端文件
2. **创建校验脚本** `check_condition_sync.py`
3. **修复当前差异**：
   - 后端 `stock_phase_up`/`bond_phase_up` 添加 `mode='critical'`

### 阶段2（后续优化）：统一配置文件

1. 设计 JSON Schema
2. 迁移条件定义
3. 前后端加载逻辑改造
4. 废弃代码内定义

---

## 立即修复项（待审核）

### 修复1：阶段条件添加 mode='critical'

**文件**：`backtest_worker.py` `_get_market_conditions()`

```python
# 修改前
{'id': 'stock_phase_up', 'name': '股票阶段(升/弹)', ...}
{'id': 'bond_phase_up', 'name': '债券阶段(升/弹)', ...}

# 修改后
{'id': 'stock_phase_up', 'name': '股票阶段(升/弹)', 'mode': 'critical', ...}
{'id': 'bond_phase_up', 'name': '债券阶段(升/弹)', 'mode': 'critical', ...}
```

### 修复2：添加同步注释

**backtest_worker.py** (line ~350):
```python
    def _get_market_conditions(self) -> list:
        """大盘条件（与前端 BP_CONDITIONS type=market 完全对应）
        
        SYNC:BP_CONDITIONS:2026-05-29
        前端对应: templates/monitor.html BP_CONDITIONS filter by type='market'
        """
```

**monitor.html** (line ~2210):
```javascript
        // SYNC:BP_CONDITIONS:2026-05-29
        // 后端对应: routes/backtest_worker.py _get_market_conditions()
        var BP_CONDITIONS = [
```

### 修复3：创建校验脚本

**文件**：`scripts/check_condition_sync.py`

功能：
- 解析前端 `BP_CONDITIONS` 数组
- 解析后端 `_get_market_conditions()`、`_get_stock_conditions()`、`_get_link_conditions()`
- 对比字段：id, type, mode, param, def
- 输出差异报告

---

## 审核确认项

1. **是否同意阶段1方案**（注释标记 + 校验脚本 + 修复 mode）？
2. **是否立即实施修复1**（添加 mode='critical'）？
3. **校验脚本是否需要**？还是采用其他同步机制？
4. **长期是否倾向方案A**（统一JSON配置）？

