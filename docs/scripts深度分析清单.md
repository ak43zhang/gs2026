# Scripts目录深度分析清单

## 总体统计

| 类别 | 数量 | 说明 |
|------|------|------|
| CHECK开头 | 19个 | 检查/验证脚本 |
| FILL开头 | 1个 | 填充数据脚本 |
| BACKFILL开头 | 5个 | 回填数据脚本 |
| TEST开头 | 29个 | 测试脚本（主要在huatai_trader） |
| FIX开头 | 2个 | 修复脚本 |
| OTHER | 74个 | 其他功能脚本 |
| **合计** | **130个** | |

---

## 一、CHECK开头脚本分析（19个）

### 建议保留（有用的检查脚本）

| 序号 | 文件名 | 用途 | 操作 |
|------|--------|------|------|
| 1 | check_anomaly_index.py | 检查异常指标 | 保留 |
| 2 | check_bond_data.py | 检查债券数据 | 保留 |
| 3 | check_columns.py | 检查列 | 保留 |
| 4 | check_detail_tables.py | 检查详情表 | 保留 |
| 5 | check_green_bond.py | 检查绿债 | 保留 |
| 6 | check_industry_data.py | 检查行业数据 | 保留 |
| 7 | check_mainline_data.py | 检查主线数据 | 保留 |
| 8 | check_mysql_locks.py | 检查MySQL锁 | 保留 |
| 9 | check_redis_wc.py | 检查Redis问财 | 保留 |
| 10 | check_redis_wc_bond.py | 检查Redis债券 | 保留 |

**小计：10个保留**

### 建议删除（一次性/过时检查）

| 序号 | 文件名 | 说明 | 操作 |
|------|--------|------|------|
| 1 | check_bond_discover.py | 债券发现检查（临时） | 删除 |
| 2 | check_bond_mainline.py | 债券主线检查（重复） | 删除 |
| 3 | check_domain_detail.py | 领域详情检查（一次性） | 删除 |
| 4 | check_industry_mapping.py | 行业映射检查（已完成） | 删除 |
| 5 | check_kb_js.py | 知识库检查（临时） | 删除 |
| 6 | check_mainline_mismatch.py | 主线不匹配检查（已修复） | 删除 |
| 7 | check_remaining.py | 剩余检查（临时） | 删除 |
| 8 | check_today_mismatch.py | 今日不匹配检查（临时） | 删除 |
| 9 | check_xilong.py | 西龙检查（特定股票） | 删除 |

**小计：9个删除**

---

## 二、FILL开头脚本分析（1个）

| 文件名 | 用途 | 操作 |
|--------|------|------|
| fill_real_bond_data.py | 填充真实债券数据 | 保留（有用） |

---

## 三、BACKFILL开头脚本分析（5个）

### 建议保留

| 序号 | 文件名 | 用途 | 操作 |
|------|--------|------|------|
| 1 | backfill_bond_v2.py | 回填债券数据V2 | 保留 |
| 2 | backfill_json_fields.py | 回填JSON字段 | 保留 |
| 3 | backfill_unified.py | 统一回填 | 保留 |

**小计：3个保留**

### 建议删除（过时/重复）

| 序号 | 文件名 | 说明 | 操作 |
|------|--------|------|------|
| 1 | backfill_bond_window_count.py | 债券窗口计数回填（过时） | 删除 |
| 2 | backfill_window_count.py | 窗口计数回填（过时） | 删除 |

**小计：2个删除**

---

## 四、TEST开头脚本分析（29个）

### 交易助手测试（huatai_trader目录）

| 类别 | 数量 | 操作 |
|------|------|------|
| 弹窗检测测试 | 15个 | 保留（交易核心功能） |
| 流程测试 | 5个 | 保留 |
| 其他测试 | 9个 | 审核后决定 |

**建议保留**：test_auto_trader.py, test_cancel_f3.py, test_cancel_tp_sl.py, test_e2e.py, test_full_flow.py 等核心测试

**建议删除**：test_dry_run.py（已合并）, test_popup_by_class.py（过时）等

---

## 五、FIX开头脚本分析（2个）

| 文件名 | 用途 | 操作 |
|--------|------|------|
| fix_notice_redis.py | 修复公告Redis | 保留（可能还有用） |
| fix_potential_unique_key.py | 修复唯一键 | 保留（可能还有用） |

---

## 六、深度清理建议

### 1. CHECK脚本删除清单（9个）

```bash
rm scripts/check_bond_discover.py
rm scripts/check_bond_mainline.py
rm scripts/check_domain_detail.py
rm scripts/check_industry_mapping.py
rm scripts/check_kb_js.py
rm scripts/check_mainline_mismatch.py
rm scripts/check_remaining.py
rm scripts/check_today_mismatch.py
rm scripts/check_xilong.py
```

### 2. BACKFILL脚本删除清单（2个）

```bash
rm scripts/backfill_bond_window_count.py
rm scripts/backfill_window_count.py
```

### 3. TEST脚本删除清单（建议删除5个）

```bash
rm scripts/huatai_trader/test_dry_run.py
rm scripts/huatai_trader/test_popup_by_class.py
rm scripts/huatai_trader/test_popup_child.py
rm scripts/huatai_trader/test_popup_debug.py
rm scripts/huatai_trader/test_popup_internal.py
```

---

## 七、清理汇总

| 类别 | 删除数量 |
|------|----------|
| CHECK脚本 | 9个 |
| BACKFILL脚本 | 2个 |
| TEST脚本 | 5个 |
| **合计** | **16个** |

---

## 八、保留脚本清单

### 核心功能脚本（保留）

| 类别 | 保留数量 | 说明 |
|------|----------|------|
| CHECK | 10个 | 数据检查 |
| FILL | 1个 | 数据填充 |
| BACKFILL | 3个 | 数据回填 |
| TEST | 24个 | 交易测试 |
| FIX | 2个 | 修复脚本 |
| OTHER | 74个 | 功能脚本 |
| **合计** | **114个** | |

---

**状态**: 🟡 待审核  
**审核后执行删除**
