# Tools目录清理清单

**分析时间**: 2026-07-25 05:06  
**目录**: `F:\pyworkspace2026\gs2026\tools`

---

## 目录概览

| 统计项 | 数值 |
|--------|------|
| 总文件数 | **252个** |
| Python脚本 | 245个 (0.55 MB) |
| SQL文件 | 4个 (0.01 MB) |
| JSON文件 | 1个 |
| TXT文件 | 1个 |
| MD文件 | 1个 (0.01 MB) |

---

## 脚本分类分析

### 1. 核心工具类 (建议保留)

| 文件名 | 用途 | 修改时间 |
|--------|------|----------|
| `console_reporter.py` | 控制台报告 | 93天前 |
| `data_cleaner.py` | 数据清理 | 93天前 |
| `data_validator.py` | 数据验证 | 93天前 |
| `engine.py` | 引擎工具 | 93天前 |
| `env_checker.py` | 环境检查 | 95天前 |
| `file_reporter.py` | 文件报告 | 93天前 |
| `models.py` | 模型定义 | 93天前 |
| `params.py` | 参数配置 | 93天前 |
| `yaml_loader.py` | YAML加载 | 93天前 |
| `auth_manager.py` | 认证管理 | 76天前 |
| `cache_manager.py` | 缓存管理 | 95天前 |
| `db_inspector.py` | 数据库检查 | 95天前 |
| `redis_checker.py` | Redis检查 | 95天前 |
| `table_validator.py` | 表验证 | 95天前 |
| `domain_validator.py` | 领域验证 | 93天前 |
| `news_validator.py` | 新闻验证 | 93天前 |
| `notice_validator.py` | 公告验证 | 93天前 |
| `ztb_validator.py` | 涨停验证 | 93天前 |
| `overnight_risk_analyzer.py` | 隔夜风险分析 | 101天前 |

**小计**: 19个文件

---

### 2. 数据库操作类 (选择性保留)

| 文件名 | 用途 | 建议 |
|--------|------|------|
| `create_table.py` | 创建表 | 检查是否常用 |
| `alter_table.py` | 修改表 | 检查是否常用 |
| `alter_accounts_table.py` | 修改账户表 | 检查是否常用 |
| `drop_old_tables.py` | 删除旧表 | **可删除** |
| `archive_monitor_tables.py` | 归档监控表 | 检查是否常用 |
| `clean_mysql_space.py` | 清理MySQL空间 | 检查是否常用 |
| `emergency_cleanup.py` | 紧急清理 | 检查是否常用 |
| `cleanup_redis_orphan.py` | 清理Redis孤儿 | **可删除** |
| `analyze_mysql_storage.py` | 分析MySQL存储 | **可删除** |
| `create_analysis_tables.py` | 创建分析表 | 检查是否常用 |

**建议**: 保留5个，删除5个

---

### 3. 检查/诊断类 (大量重复，建议清理)

**check_ 开头的脚本 (约60个)**

| 类别 | 数量 | 建议 |
|------|------|------|
| check_*.py (各种检查) | 60+个 | **大部分可删除** |
| 包括: check_bond_*.py, check_redis_*.py, check_data*.py 等 | | |

**debug_ 开头的脚本 (约15个)**

| 文件名 | 建议 |
|--------|------|
| debug_*.py (各种调试) | **全部可删除** |
| debug_bond_*.py | 临时调试 |
| debug_8080_api.py | 临时调试 |
| debug_db_profiler.py | 临时调试 |

**test_ 开头的脚本 (约50个)**

| 类别 | 数量 | 建议 |
|------|------|------|
| test_*.py (各种测试) | 50+个 | **大部分可删除** |
| test_api*.py | 5个 | 保留1个 |
| test_bond*.py | 5个 | 保留1个 |
| test_chinese.py | 1个 | **删除** |
| test_code_*.py | 2个 | **删除** |
| test_collection*.py | 1个 | **删除** |
| test_cross*.py | 2个 | **删除** |
| test_detail*.py | 2个 | **删除** |
| test_domain*.py | 2个 | **删除** |
| test_enrich.py | 1个 | **删除** |
| test_hot_sectors.py | 1个 | **删除** |
| test_industry*.py | 1个 | **删除** |
| test_meinuo.py | 1个 | **删除** |
| test_monitor*.py | 1个 | **删除** |
| test_news*.py | 3个 | **删除** |
| test_order.py | 1个 | **删除** |
| test_pandas*.py | 1个 | **删除** |
| test_price*.py | 2个 | **删除** |
| test_process*.py | 1个 | **删除** |
| test_pymysql*.py | 1个 | **删除** |
| test_rank*.py | 2个 | **删除** |
| test_redis.py | 1个 | **删除** |
| test_routes.py | 1个 | **删除** |
| test_search*.py | 2个 | **删除** |
| test_service*.py | 2个 | **删除** |
| test_single*.py | 1个 | **删除** |
| test_sql.py | 1个 | **删除** |
| test_st*.py | 2个 | **删除** |
| test_start_monitor.py | 1个 | **删除** |
| test_stock_picker*.py | 2个 | **删除** |
| test_time_issue.py | 1个 | **删除** |
| test_types.py | 1个 | **删除** |
| test_yinhe*.py | 3个 | **删除** |
| test_ztb*.py | 2个 | **删除** |

---

### 4. 修复/填充类 (一次性脚本，可删除)

| 文件名 | 建议 |
|--------|------|
| fix_*.py (约20个) | **全部可删除** |
| fill_*.py (约5个) | **全部可删除** |
| backfill_*.py | **可删除** |
| insert_*.py | **可删除** |
| add_*.py (约5个) | **可删除** |
| rewrite_*.py (2个) | **可删除** |
| rollback_*.py | **可删除** |
| remove_dup_func.py | **可删除** |

---

### 5. 验证类 (可删除)

| 文件名 | 建议 |
|--------|------|
| verify_*.py (约8个) | **全部可删除** |
| compare_*.py | **可删除** |
| diagnose_*.py | **可删除** |
| simulate_*.py (2个) | **可删除** |
| view_process_monitor.py | **可删除** |

---

### 6. 其他临时脚本

| 文件名 | 建议 |
|--------|------|
| api_tester.py | **可删除** |
| append_timepoint.py | **可删除** |
| delete_today.py | **可删除** |
| dump_render*.py (2个) | **可删除** |
| find_*.py (4个) | **可删除** |
| generate_*.py | **可删除** |
| implement_*.py | **可删除** |
| pinpoint_bottleneck.py | **可删除** |
| profile_stock_ranking.py | **可删除** |
| refresh_and_verify.py | **可删除** |
| refresh_cache.py | **可删除** |
| search_door.py | **可删除** |
| update_recent_api.py | **可删除** |
| write_single_timepoint*.py (2个) | **可删除** |

---

## 清理建议汇总

### 方案A：激进清理（推荐）

| 类别 | 数量 | 操作 |
|------|------|------|
| 核心工具 | 19个 | **保留** |
| 数据库操作 | 5个 | **保留** |
| check_* 脚本 | 55个 | **删除** |
| debug_* 脚本 | 15个 | **删除** |
| test_* 脚本 | 48个 | **删除** |
| fix_* 脚本 | 20个 | **删除** |
| fill_* 脚本 | 5个 | **删除** |
| verify_* 脚本 | 8个 | **删除** |
| 其他临时脚本 | 70个 | **删除** |
| **合计** | **245个** | **保留24个，删除221个 (90%)** |

### 保留清单 (24个)

```
console_reporter.py
data_cleaner.py
data_validator.py
engine.py
env_checker.py
file_reporter.py
models.py
params.py
yaml_loader.py
auth_manager.py
cache_manager.py
db_inspector.py
redis_checker.py
table_validator.py
domain_validator.py
news_validator.py
notice_validator.py
ztb_validator.py
overnight_risk_analyzer.py
create_table.py
alter_table.py
alter_accounts_table.py
archive_monitor_tables.py
clean_mysql_space.py
```

---

## 实施步骤

### 步骤1：创建备份目录
```bash
mkdir -p tools/temp_backup
```

### 步骤2：移动保留文件
```bash
# 保留核心工具
mv tools/console_reporter.py tools/temp_backup/
mv tools/data_cleaner.py tools/temp_backup/
mv tools/data_validator.py tools/temp_backup/
mv tools/engine.py tools/temp_backup/
mv tools/env_checker.py tools/temp_backup/
mv tools/file_reporter.py tools/temp_backup/
mv tools/models.py tools/temp_backup/
mv tools/params.py tools/temp_backup/
mv tools/yaml_loader.py tools/temp_backup/
mv tools/auth_manager.py tools/temp_backup/
mv tools/cache_manager.py tools/temp_backup/
mv tools/db_inspector.py tools/temp_backup/
mv tools/redis_checker.py tools/temp_backup/
mv tools/table_validator.py tools/temp_backup/
mv tools/domain_validator.py tools/temp_backup/
mv tools/news_validator.py tools/temp_backup/
mv tools/notice_validator.py tools/temp_backup/
mv tools/ztb_validator.py tools/temp_backup/
mv tools/overnight_risk_analyzer.py tools/temp_backup/
mv tools/create_table.py tools/temp_backup/
mv tools/alter_table.py tools/temp_backup/
mv tools/alter_accounts_table.py tools/temp_backup/
mv tools/archive_monitor_tables.py tools/temp_backup/
mv tools/clean_mysql_space.py tools/temp_backup/
```

### 步骤3：删除其他所有.py文件
```bash
# 删除check_*.py
rm tools/check_*.py

# 删除debug_*.py
rm tools/debug_*.py

# 删除test_*.py (保留少量有用的)
rm tools/test_*.py

# 删除fix_*.py
rm tools/fix_*.py

# 删除fill_*.py
rm tools/fill_*.py

# 删除其他临时脚本
rm tools/api_tester.py
rm tools/append_timepoint.py
rm tools/backfill_*.py
rm tools/compare_*.py
rm tools/delete_today.py
rm tools/diagnose_*.py
rm tools/dump_*.py
rm tools/emergency_cleanup.py
rm tools/find_*.py
rm tools/generate_*.py
rm tools/implement_*.py
rm tools/insert_*.py
rm tools/pinpoint_*.py
rm tools/profile_*.py
rm tools/refresh_*.py
rm tools/remove_*.py
rm tools/rewrite_*.py
rm tools/rollback_*.py
rm tools/search_*.py
rm tools/simulate_*.py
rm tools/update_*.py
rm tools/verify_*.py
rm tools/view_*.py
rm tools/write_*.py
rm tools/cleanup_*.py
rm tools/analyze_*.py
rm tools/create_analysis_tables.py
rm tools/drop_old_tables.py
rm tools/emergency_cleanup.py
rm tools/fill_*.py
rm tools/fix_*.py
rm tools/insert_*.py
rm tools/remove_*.py
rm tools/rewrite_*.py
rm tools/rollback_*.py
rm tools/simulate_*.py
rm tools/verify_*.py
```

### 步骤4：恢复保留文件
```bash
mv tools/temp_backup/* tools/
rmdir tools/temp_backup
```

---

## 清理后结构

```
tools/
├── __init__.py (保留)
├── console_reporter.py
├── data_cleaner.py
├── data_validator.py
├── engine.py
├── env_checker.py
├── file_reporter.py
├── models.py
├── params.py
├── yaml_loader.py
├── auth_manager.py
├── cache_manager.py
├── db_inspector.py
├── redis_checker.py
├── table_validator.py
├── domain_validator.py
├── news_validator.py
├── notice_validator.py
├── ztb_validator.py
├── overnight_risk_analyzer.py
├── create_table.py
├── alter_table.py
├── alter_accounts_table.py
├── archive_monitor_tables.py
├── clean_mysql_space.py
└── [其他非.py文件保留]
```

---

**状态**: 🟡 待审核  
**建议**: 实施方案A，删除221个临时脚本，保留24个核心工具
