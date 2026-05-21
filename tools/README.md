# GS2026 工具集

项目诊断、维护和运维工具集合。

## 工具清单

### 数据库诊断

| 工具 | 功能 | 示例 |
|------|------|------|
| `db_inspector.py` | 检查表结构、索引、数据量 | `python tools/db_inspector.py --table monitor_gp_sssj_20260515` |
| `table_validator.py` | 验证表数据完整性 | `python tools/table_validator.py --check-bond` |
| `analyze_mysql_storage.py` | 分析MySQL存储占用（表大小、索引大小） | `python tools/analyze_mysql_storage.py` |

### Redis 管理

| 工具 | 功能 | 示例 |
|------|------|------|
| `redis_checker.py` | 检查Redis键、内存 | `python tools/redis_checker.py --pattern "domain:*" --stats` |

### API 测试

| 工具 | 功能 | 示例 |
|------|------|------|
| `api_tester.py` | 测试API接口 | `python tools/api_tester.py --test-stock-picker` |

### 缓存管理

| 工具 | 功能 | 示例 |
|------|------|------|
| `cache_manager.py` | 管理内存/宽表缓存 | `python tools/cache_manager.py --warm-up` |

### 环境检查

| 工具 | 功能 | 示例 |
|------|------|------|
| `env_checker.py` | 检查运行环境 | `python tools/env_checker.py` |

### 数据归档

| 工具 | 功能 | 示例 |
|------|------|------|
| `archive_monitor_tables.py` | MySQL监控表归档为Parquet | `python tools/archive_monitor_tables.py --scan` |
| `test_archive_restore.py` | 验证Parquet归档可还原 | `python tools/test_archive_restore.py` |

### 数据生成与映射

| 工具 | 功能 | 示例 |
|------|------|------|
| `generate_stock_bond_mapping.py` | 生成股票-债券-行业映射 | `python tools/generate_stock_bond_mapping.py` |

### 风险分析

| 工具 | 功能 | 示例 |
|------|------|------|
| `overnight_risk_analyzer.py` | 隔夜风险分析 | `python tools/overnight_risk_analyzer.py` |

### 买点回溯

| 工具 | 功能 | 示例 |
|------|------|------|
| `backfill_buy_points.py` | 按真实逻辑回填历史买点候选 | `python tools/backfill_buy_points.py --date 20260519` |

**回填参数：**
```bash
# 全量回填（每3秒，耗时约20分钟）
python tools/backfill_buy_points.py --date 20260519

# 指定时间范围
python tools/backfill_buy_points.py --date 20260519 --start 09:30:00 --end 10:00:00

# 仅预览不写入
python tools/backfill_buy_points.py --date 20260519 --dry-run

# 30秒间隔采样（更快，约2分钟）
python tools/backfill_buy_points.py --date 20260519 --interval 30

# 清除旧数据后回填
python tools/backfill_buy_points.py --date 20260519 --clear
```

**条件逻辑（与前端 BP_CONDITIONS 一致）：**
- 必要条件（全部通过）：主力/峰值>0.9, 涨幅>2%, 连续上攻>0, 债券在排行
- 加分条件（决定星级）：行业前10, 债券涨幅>2%
- 星级 = 1 + min(bonus, 2)，只保存 ≥2星

### 紧急维护

| 工具 | 功能 | 示例 |
|------|------|------|
| `emergency_cleanup.py` | 紧急清理（磁盘/表/缓存） | `python tools/emergency_cleanup.py` |
| `auth_manager.py` | 认证管理 | `python tools/auth_manager.py` |

### SQL 迁移脚本

| 脚本 | 功能 |
|------|------|
| `create_report_tables.sql` | 创建报表相关表 |
| `migrate_cumulative_main_net.sql` | 累计主力净额字段迁移 |
| `migrate_main_force_fields.sql` | 主力资金字段迁移 |

---

## 快速开始

```bash
# 检查环境
python tools/env_checker.py

# 预热缓存
python tools/cache_manager.py --warm-up

# 验证数据
python tools/table_validator.py --check-bond

# 测试API
python tools/api_tester.py --test-all
```

---

## 常用运维操作

### 1. MySQL 存储分析

分析数据库存储占用，识别大表：

```bash
python tools/analyze_mysql_storage.py
```

输出：各表大小、索引大小、总计，按大小排序。

### 2. 监控表归档

将过期监控表归档为 Parquet 文件，释放 MySQL 空间：

```bash
# 扫描可归档的表（仅查看，不执行）
python tools/archive_monitor_tables.py --scan

# 执行归档（需确认）
python tools/archive_monitor_tables.py --archive

# 归档后验证
python tools/test_archive_restore.py
```

**归档规则**：
- 默认归档 30 天前的监控表
- 归档目录：`D:\gsdata2\mysql_achieve`
- 每张表一个目录，Parquet 按 128MB 分片
- 归档后自动验证行数一致性，验证通过才删除原表

### 3. 股债映射生成

生成/更新股票-债券-行业映射关系：

```bash
python tools/generate_stock_bond_mapping.py
```

### 4. 紧急清理

磁盘空间不足或系统异常时使用：

```bash
python tools/emergency_cleanup.py
```

---

## 目录结构

```
tools/
├── README.md                          # 本文件
├── analyze_mysql_storage.py           # MySQL 存储分析
├── archive_monitor_tables.py          # 监控表归档工具
├── test_archive_restore.py            # 归档还原测试
├── generate_stock_bond_mapping.py     # 股债映射生成
├── overnight_risk_analyzer.py         # 隔夜风险分析
├── backfill_buy_points.py             # 买点候选回填工具
├── emergency_cleanup.py               # 紧急清理
├── db_inspector.py                    # 数据库检查
├── table_validator.py                 # 表数据验证
├── redis_checker.py                   # Redis 检查
├── api_tester.py                      # API 测试
├── cache_manager.py                   # 缓存管理
├── auth_manager.py                    # 认证管理
├── env_checker.py                     # 环境检查
├── create_report_tables.sql           # 报表建表 SQL
├── migrate_cumulative_main_net.sql    # 累计主力净额迁移
├── migrate_main_force_fields.sql      # 主力资金字段迁移
└── archive/                           # 归档清单目录
```

## 注意事项

- 所有工具需在项目根目录执行：`cd F:\pyworkspace2026\gs2026`
- Python 路径：`F:\python312\python.exe`
- 数据库连接配置在 `src/gs2026/utils/config_util.py` 中
- **归档操作不可逆**，请在非交易时间执行并确认验证通过
