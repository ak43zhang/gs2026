# sssj 表查询未命中 WARNING — 根因定位与修复方案

## 一、问题现象

```
2026-08-03 09:34:41 | WARNING | redis_util:load_dataframe_by_key:244 |
键 monitor_zq_sssj_20260803:09:34:41 不存在或已过期
```

## 二、根因（Redis 现场实测确认，非推测）

### 2.1 决定性证据

实测 Redis（10:01 稳定运行时）：
- **`09:34:41` 不在任何表的 timestamps 列表中**（债券/股票/行业的 sssj/top30/apqd 全都没有）。
- 所有真实采集时间戳都是 **3 秒对齐**：`:03 :06 :09 :12 :15 :18 ...`（债券 tick 周期 3 秒）。
- `09:34:41` 的 `:41` 秒**不在 3 秒网格上** → 它根本不是任何一次采集的时刻。
- 盘初 09:30-09:36 的 120 个真实时间戳，数据 key **全部存在，零缺失**（排除"写入失败/异步滞后"）。

### 2.2 真凶代码

`dashboard2/routes/monitor.py` 债券上攻排行接口（约 line 2005-2020）：

```python
else:
    # 当日实时模式：使用当前时间
    query_time = datetime.now().strftime('%H:%M:%S')   # ← 墙上时钟 09:34:41
    use_mysql = True
    data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)

data = _enrich_bond_data(data, actual_date, query_time)   # ← 用 09:34:41 查 sssj
```

`_enrich_bond_data` 内部本有正确 fallback（取 sssj `:timestamps` 最新值），但**仅在 `time_str` 为空时生效**：

```python
if time_str:                    # 传了 09:34:41（非空）→ 直接用，跳过正确逻辑
    query_time = time_str
else:                           # 只有为空才取 sssj 最新已就绪时间戳
    latest_ts = client.lindex(f"monitor_zq_sssj_{date}:timestamps", 0)
```

### 2.3 根因结论

**债券实时模式把"墙上时钟当前时刻"`datetime.now()`（如 09:34:41）当作查询时间传给 `_enrich_bond_data`，旁路了它内部"取 sssj 最新已就绪时间戳"的正确逻辑。** 而债券 tick 只在 3 秒对齐时刻采集，`09:34:41` 无对应 sssj 数据 → 未命中 WARNING → 降级 MySQL（慢、压库）。

> 注：与最初"异步写入滞后"的猜测无关——现场证据显示同 tick 数据零缺失、读写完全同步。问题纯粹是**查询时间戳取错了源**。

## 三、修复方案

### 方案（唯一正解，最小改动）：实时模式用 sssj 最新已就绪时间戳，不用 now()

`query_time` 不再用 `datetime.now()`，而是复用 `_enrich_bond_data` 已有的正确逻辑——**传 `time_str=None`，让它自己取 sssj `:timestamps` 最新值**。

**改法（债券接口 line ~2005-2020）**：
```python
else:
    # 当日实时模式：不使用墙上时钟，交给 _enrich_bond_data 取 sssj 最新就绪时间戳
    query_time = None      # ← 关键：置空，触发内部正确 fallback
    data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=True)

data = _enrich_bond_data(data, actual_date, query_time)  # time_str=None → 取 sssj 最新时间戳
```

### 同源排查：股票 / 行业接口

`monitor.py` 内多处 `query_time = datetime.now().strftime('%H:%M:%S')`：
- line 1896：`_enrich_stock_data(data, ..., datetime.now().strftime("%H:%M:%S"))` — **同样问题**，股票 tick 也 3 秒对齐，`now()` 会错位。
- line 2007：债券（本次主因）。
- 其余 now() 用于 date（`%Y%m%d`）或存储 save_time，不涉及 sssj 查询，无需改。

**建议一并修复股票侧**（line 1896），逻辑同债券：传 None 让 `_enrich_stock_data` 取 `monitor_gp_sssj_{date}:timestamps` 最新值。需先确认 `_enrich_stock_data` 是否也有"time_str 为空时取 timestamps"的 fallback（若无则需补）。

### 日志降噪（可选）

`load_dataframe_by_key`（line 244）的"键不存在"WARNING，在有 MySQL 兜底的场景属预期噪音。可降为 debug 或加 `quiet` 参数。修好时间戳后此告警本就会消失，降噪为次要项。

## 四、验证计划

1. 实测 Redis：确认 `_enrich_bond_data`(time_str=None) 取到的是 3 秒对齐的最新时间戳（如 `10:01:18`），且该 sssj key 必然存在。
2. 盘中观察：`monitor_zq_sssj_...:xx 不存在` WARNING 消失。
3. 债券/股票上攻排行明细（涨跌幅/价格/金额）正常，与最新 tick 一致。
4. 历史回放（带 time_str）路径不受影响。
5. AST 查 monitor.py 重复函数定义（历史教训）。

## 五、待用户确认

- 是否**债券 + 股票一并修复**（都改为取 sssj 最新就绪时间戳）？
- 是否确认 `_enrich_stock_data` 的 fallback 逻辑（我实施前会先读它，若缺 fallback 会补齐）。
- WARNING 是否顺带降为 debug？

---

## 六、实施记录（已完成）

### 用户追问：为什么股票能展示、债券不能？

HTTP 实测对比（修复前）：
| | 债券 | 股票 |
|---|---|---|
| success / count | True / 61 | True / 509 |
| **change_pct** | **全是 `-`** | 正常（10.0 等） |

**答**：两者都返回数据，但债券**涨跌幅字段全为 `-`**（看似"展示不出来"）。差异根源：
- 股票涨跌幅由 `_enrich_change_pct_and_main_net` 处理，调用时**未传 time_str** → 内部走 `_get_latest_sssj_time()` 取真实 3 秒对齐时间戳 → 正常。
- 债券涨跌幅由 `_enrich_bond_data` 处理，调用时**传了 `datetime.now()`（09:34:41）** → 不在债券采集网格 → 查不到 → 全 `-`。

### 最终修复（最小改动，纯 bug 修复）

`monitor.py` `get_bond_ranking` 实时分支：
```python
# 修复前
query_time = datetime.now().strftime('%H:%M:%S')
# 修复后
query_time = None   # 交给 _enrich_bond_data 内部取 sssj 最新时间戳
```

**不影响任何逻辑**：`_enrich_bond_data` 的 `time_str=None` 分支是既有代码（取 `monitor_zq_sssj:timestamps` 最新值）；`_mark_and_sort_realtime_attacks` 本就传 time_str=None 不变；历史回放路径不碰；股票侧不改。

### 验证（HTTP 实测，修复后）
| | change_pct |
|---|---|
| 债券 | `-2.3889` / `10.4945` / `4.9486` ✅ |
| 股票 | 正常 ✅（不受影响） |

- `ast.parse` 语法 OK
- 债券实时分支不再用 now() 查询 ✅

### 遗留（非本次范围，仅记录）
AST 扫出 monitor.py 既有重复函数定义（与本 bug 无关）：
- `_get_bond_change_pct_from_mysql`（line 824 / 2741）
- `get_recent_buy_points`（line 3618 / 3699）
后定义覆盖前定义。建议后续单独清理，本次按"只修此 bug"原则未动。
