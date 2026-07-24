# scripts目录临时脚本清理方案

## 扫描结果

| 统计项 | 数量 |
|--------|------|
| 总脚本数 | 79个 |
| 疑似临时脚本 | 21个 |

---

## 建议清理的临时脚本清单

### 1. 测试脚本（13个）
这些脚本用于临时测试，测试完成后可删除：

| 脚本路径 | 说明 |
|----------|------|
| `test_api_window_count.py` | API窗口计数测试 |
| `test_cls_api.py` | 财联社API测试 |
| `test_cls_error.py` | 财联社错误测试 |
| `test_distributed_lock.py` | 分布式锁测试 |
| `test_extract_text.py` | 文本提取测试 |
| `test_potential.py` | 潜力股测试 |
| `test_zskj.py` | 中科金财测试 |
| `test_zt_limit.py` | 涨停限制测试 |
| `huatai_trader/test_e2e.py` | 端到端测试 |
| `huatai_trader/test_full_flow.py` | 全流程测试 |
| `huatai_trader/test_tdx_source.py` | TDX数据源测试 |

### 2. 验证脚本（6个）
这些脚本用于数据验证，验证完成后可删除：

| 脚本路径 | 说明 |
|----------|------|
| `verify_and_fix_bond_window_count.py` | 验证并修复债券窗口计数 |
| `verify_cache_date.py` | 验证缓存日期 |
| `verify_dedup.py` | 验证去重 |
| `verify_green_bond_query.py` | 验证绿债查询 |
| `verify_stock_window_count.py` | 验证股票窗口计数 |

### 3. 清理/插入脚本（2个）
一次性清理/插入脚本：

| 脚本路径 | 说明 |
|----------|------|
| `cleanup_browser_path.py` | 清理浏览器路径 |
| `cleanup_string_enum.py` | 清理字符串枚举 |
| `insert_mock_potential.py` | 插入模拟潜力数据 |

### 4. 其他临时脚本（1个）

| 脚本路径 | 说明 |
|----------|------|
| `check_disk_usage.py` | 检查磁盘使用 |
| `scan_temp.py` | 本次扫描脚本本身 |

---

## 清理建议

### 方案A：全部删除（推荐）
删除全部21个临时脚本，保持scripts目录整洁。

### 方案B：保留测试脚本
- 删除：清理/插入脚本（3个）+ 验证脚本（6个）+ 其他（2个）= 11个
- 保留：测试脚本（10个）用于后续测试

### 方案C：移动到tests目录
将测试脚本移动到 `tests/` 目录统一管理。

---

## 推荐方案

**方案A（全部删除）**，原因：
1. 这些脚本都是一次性使用的工具
2. 测试脚本如果还需要可以从git历史恢复
3. 验证脚本验证完成后无保留价值
4. 保持scripts目录只保留核心功能脚本

---

## 保留的核心脚本（58个）

```
scripts/
├── add_anomaly_indexes.py
├── add_chaoduan_column.py
├── add_expectation_fields.py
├── add_filtered_stats.py
├── add_kb_js_to_profile.py
├── add_replay_time_column.py
├── add_retry_count.py
├── add_tick_up_func.py
├── add_window_count_func.py
├── backfill_bond_v2.py
├── backfill_bond_window_count.py
├── backfill_unified.py
├── backfill_window_count.py
├── check_anomaly_index.py
├── check_bond_data.py
├── check_bond_discover.py
├── check_bond_mainline.py
├── check_columns.py
├── check_detail_tables.py
├── check_domain_detail.py
├── check_green_bond.py
├── check_industry_data.py
├── check_industry_mapping.py
├── check_kb_js.py
├── check_mainline_data.py
├── check_mainline_mismatch.py
├── check_mysql_locks.py
├── check_redis_wc.py
├── check_redis_wc_bond.py
├── check_today_mismatch.py
├── check_xilong.py
├── compute_engine.py
├── create_kb_table.py
├── create_mainline_tables.py
├── create_potential_table.py
├── debug_window_count.py
├── debug_zskj.py
├── drop_correlation_context.py
├── drop_old_monitor_tables.py
├── embed_kb_in_profile.py
├── field_registry.py
├── fix_green_bond_at_time.py
├── fix_imports.py
├── fix_kb_issues.py
├── fix_kb_quotes.py
├── fix_marked_cdn.py
├── fix_notice_redis.py
├── fix_potential_unique_key.py
├── list_tables_to_delete.py
├── remove_tick_up.py
├── replace_nav.py
├── seed_anomaly_data.py
├── trigger_potential.py
└── huatai_trader/
    ├── __init__.py
    ├── main.py
    ├── popup.py
    ├── server.py
    ├── trader.py
    ├── notify.mp3
    ├── huatai_trader.log
    ├── 交易助手.log
    ├── 依赖清单.txt
    ├── 接入指南.md
    └── 设计文档.md
```

---

## 实施命令

```bash
cd F:\pyworkspace2026\gs2026\scripts

# 删除测试脚本
del test_api_window_count.py
del test_cls_api.py
del test_cls_error.py
del test_distributed_lock.py
del test_extract_text.py
del test_potential.py
del test_zskj.py
del test_zt_limit.py
del huatai_trader\test_e2e.py
del huatai_trader\test_full_flow.py
del huatai_trader\test_tdx_source.py

# 删除验证脚本
del verify_and_fix_bond_window_count.py
del verify_cache_date.py
del verify_dedup.py
del verify_green_bond_query.py
del verify_stock_window_count.py

# 删除清理/插入脚本
del cleanup_browser_path.py
del cleanup_string_enum.py
del insert_mock_potential.py

# 删除其他临时脚本
del check_disk_usage.py
del scan_temp.py

# Git提交
cd F:\pyworkspace2026\gs2026
git add -A
git commit -m "chore: 清理scripts目录临时脚本"
```

---

**审核状态**: 待审核
