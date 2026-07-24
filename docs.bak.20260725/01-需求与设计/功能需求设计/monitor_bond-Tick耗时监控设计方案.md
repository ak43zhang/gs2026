# monitor_bond.py Tick耗时监控设计方案

## 现状分析

### monitor_stock.py 的耗时监控实现
在 `monitor_stock.py` 中，每个tick的耗时监控如下：

```python
# ========== 【性能监控】Tick周期总计 ==========
tick_total = (time.time() - tick_start) * 1000
logger.info(f"[{time_full}] Tick总计: {tick_total:.1f}ms | "
            f"采集{t1_elapsed:.1f}ms | 清洗{t2_elapsed:.1f}ms | "
            f"恢复{t3_elapsed:.1f}ms | 开盘{t4_elapsed:.1f}ms | "
            f"主力{t5_elapsed:.1f}ms | 保存{t6_elapsed:.1f}ms")
```

**特点**：
- 分阶段计时（采集、清洗、恢复、开盘、主力、保存）
- 毫秒级精度
- 统一日志输出

### monitor_bond.py 的现状
当前 `monitor_bond.py` 缺少类似的耗时监控，需要添加。

---

## 设计方案

### 方案A：完全参考monitor_stock.py（推荐）

在 `monitor_bond.py` 的 `main_loop` 函数中添加分阶段计时：

```python
def main_loop(engine, loop_start, date_str, time_full, df_bonds):
    """主循环：获取、处理、存储债券数据"""
    tick_start = time.time()  # 【新增】tick开始时间
    
    # ========== 阶段1：数据采集 ==========
    t1 = time.time()
    df_now = get_bond(data_source='tdx')  # 或 'jsl'/'adata'
    t1_elapsed = (time.time() - t1) * 1000
    
    if df_now is None or df_now.empty:
        logger.warning(f"[{time_full}] 未获取到债券数据")
        return
    
    # ========== 阶段2：数据清洗 ==========
    t2 = time.time()
    df_now = clean_bond_data(df_now)
    t2_elapsed = (time.time() - t2) * 1000
    
    # ========== 阶段3：指标计算 ==========
    t3 = time.time()
    # 趋势指标、大盘指标、扩展指标
    df_now = compute_indicators(df_now, date_str, engine=engine)
    df_now = compute_market_indicators(df_now, date_str)
    df_now = compute_ext_indicators(df_now, time_full, date_str)
    t3_elapsed = (time.time() - t3) * 1000
    
    # ========== 阶段4：量化选债筛选 ==========
    t4 = time.time()
    run_quant_screen_on_tick(df_now, date_str, time_full, engine)
    t4_elapsed = (time.time() - t4) * 1000
    
    # ========== 阶段5：数据存储 ==========
    t5 = time.time()
    msac.save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
    t5_elapsed = (time.time() - t5) * 1000
    
    # ========== 阶段6：大盘强度计算 ==========
    t6 = time.time()
    # 获取前30秒数据
    df_prev = redis_util.load_dataframe_by_offset(...)
    culculate_zq_apqd_top30(df_now, df_prev, date_str, time_full, loop_start)
    t6_elapsed = (time.time() - t6) * 1000
    
    # ========== 【性能监控】Tick周期总计 ==========
    tick_total = (time.time() - tick_start) * 1000
    logger.info(f"[债券-{time_full}] Tick总计: {tick_total:.1f}ms | "
                f"采集{t1_elapsed:.1f}ms | 清洗{t2_elapsed:.1f}ms | "
                f"指标{t3_elapsed:.1f}ms | 选债{t4_elapsed:.1f}ms | "
                f"保存{t5_elapsed:.1f}ms | 大盘{t6_elapsed:.1f}ms")
```

**优点**：
- 与monitor_stock.py风格一致
- 分阶段清晰，便于性能分析
- 毫秒级精度

---

### 方案B：简化版（只监控总耗时）

```python
def main_loop(engine, loop_start, date_str, time_full, df_bonds):
    tick_start = time.time()
    
    # ... 原有逻辑 ...
    
    tick_total = (time.time() - tick_start) * 1000
    logger.info(f"[债券-{time_full}] Tick耗时: {tick_total:.1f}ms")
```

**优点**：简单快速
**缺点**：无法定位性能瓶颈

---

### 方案C：可配置监控（高级）

添加配置项控制是否启用详细监控：

```python
# 在配置文件中添加
BOND_PERFORMANCE_MONITOR = True  # 启用详细性能监控

# 代码中
if config.get('BOND_PERFORMANCE_MONITOR', False):
    # 详细分阶段监控
else:
    # 简化监控
```

---

## 推荐方案

**方案A（完全参考monitor_stock.py）**

理由：
1. 与股票监控风格一致，便于统一维护
2. 分阶段监控便于定位性能瓶颈
3. 债券监控也需要关注数据采集、指标计算等阶段的耗时

---

## 实施步骤

1. 在 `main_loop` 函数开头添加 `tick_start = time.time()`
2. 在各阶段添加计时点
3. 在函数末尾添加统一的性能日志输出
4. 测试验证

---

## 预期输出示例

```
[债券-09:31:15] Tick总计: 850.3ms | 采集320.5ms | 清洗45.2ms | 指标180.3ms | 选债120.8ms | 保存45.1ms | 大盘138.4ms
[债券-09:31:30] Tick总计: 780.2ms | 采集280.1ms | 清洗42.5ms | 指标165.8ms | 选债110.2ms | 保存40.3ms | 大盘141.3ms
```

---

**审核状态**: 待审核
