# 债券绿名单系统（green_bond）

纯 MySQL 查询 + pandas 逻辑计算，生成 `green_bond_list` 表。可扩展多模式架构（策略模式 + 注册表）。

## 目录结构

```
green_bond/
├── runner.py          # 主入口：编排流程 + CLI
├── verify.py          # 一致性验收：新系统产出 vs 现有表比对
├── context.py         # 共享上下文（日行情 + 窗口指标惰性计算）
├── calendar.py        # 交易日历：批量 next_trade_date 映射
├── base.py            # 策略抽象基类
├── registry.py        # 策略注册表（@register）
├── repository.py      # 数据访问层（所有 SQL 集中）
└── strategies/        # 各模式策略（一文件一模式）
    ├── __init__.py    # 导入所有策略触发注册
    ├── model01_zgzf.py
    └── model02_stzf_sum.py
```

## 运行

```bash
# 全量重算（清空表重建，对齐 Scala 行为）
python -m gs2026.tools.green_bond.runner --mode full

# 增量（只重算指定 buy_date 范围，历史不动）
python -m gs2026.tools.green_bond.runner --mode incremental --start 2026-08-01 --end 2026-08-03

# 一致性验收
python -m gs2026.tools.green_bond.verify --snapshot
```

## 数据源与产出

- 输入：`data_bond_daily_ods`（日行情：zgzf/stzf/spzf/... 等）、`data_jyrl`（交易日历）
- 输出：`green_bond_list(code VARCHAR, buy_date DATE, model VARCHAR)`，唯一索引 `uk_code_buydate(code, buy_date)`
- `buy_date` = 触发日的下一个交易日
- 同一 code+buy_date 去重取 model 最小

## 模式清单

| model | 名称 | 触发条件 | 用到字段 | 阈值 | 状态 | 上线日期 |
|---|---|---|---|---|---|---|
| 1 | 当日最高涨幅 | 当日 zgzf > 4 | zgzf | 4.0 | 启用 | 2026-08-03（复刻） |
| 2 | 前两日实体涨幅和 | prev1_stzf+prev2_stzf > 4 且均 > 0 | stzf | 4.0 / 0.0 | 启用 | 2026-08-03（复刻） |
| 3 | 强赎预警 | A:已公告强赎且最后交易日≤14天; B:天计数进度≥67%; C:到期日≤60天 | data_bond_qs_jsl:最后交易日/强赎状态/强赎天计数/到期日 | 14天/67%/60天 | 启用 | 2026-08-03 |

**模式3参数设定原因（业界标准+宽松）：**
- `days_to_last_trade=14`: 两周预警期，给投资者充足时间应对强赎公告，非紧急7天
- `trigger_progress=0.67`: 强赎触发条件满足2/3即预警（10/15天），而非80%或100%，提前发现潜在强赎
- `near_expiry_days=60`: 两个月到期预警，覆盖回售期前窗口，公司可能强赎促转股，非严格30天

> 每次增删模式必须同步更新此表。

## 新增模式流程（SOP）

1. 确定模式定义：触发条件、字段、阈值、model 编号（全局唯一、字符串、不可复用历史编号）。
2. 新建 `strategies/modelNN_xxx.py`：
   ```python
   from gs2026.tools.green_bond.base import GreenBondStrategy
   from gs2026.tools.green_bond.registry import register

   @register
   class ModelNNXxx(GreenBondStrategy):
       model = "N"
       name = "模式描述"
       params = {"threshold": ...}

       def evaluate(self, ctx):
           w = ctx.windowed          # 或 ctx.bond_daily
           hit = w[<你的条件>]
           return hit[["code", "trigger_date"]].copy()
   ```
3. 在 `strategies/__init__.py` 增加一行 `from . import modelNN_xxx`。
4. （可选）若需新 lag 指标，在 `context.py::_compute_window_metrics` 补充列（所有模式共享）。
5. 跑验证：`runner --mode incremental --start <日期> --end <日期>`，检查该 model 产出。
6. 更新本 README 的"模式清单"表格。
7. 上线（接入定时任务）。

**约束**：model 编号上线后不可复用/改语义；新增只允许"新文件+注册+可选扩列"，禁改主流程；evaluate 必须纯函数（不写库）。

## 删除/下线模式流程（SOP）

1. 评估消费端依赖（现状消费端只按 buy_date 查 code，不区分 model，通常无影响）。
2. 停止产出（二选一）：
   - **软下线（推荐）**：策略类设 `enabled = False`，注册表自动跳过。保留代码与历史，可回滚。
   - **硬删除**：删策略文件 + 移除 `strategies/__init__.py` 的 import。
3. 历史数据（三选一）：保留 / `DELETE FROM green_bond_list WHERE model='N'`（先备份）/ full 重算覆盖。
4. 更新 README 模式清单，标注"已下线（日期+原因）"。
5. 下线的 model 编号不回收复用。

**约束**：软下线优先；删除不得影响其他模式；清理历史前必须备份（先 snapshot 基线表再 DELETE）。
