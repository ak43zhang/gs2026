# Dashboard2 开发总结 (2026-03-31 至 2026-04-01)

## 概述

本文档总结了Dashboard2调度中心及相关模块在2026年3月31日至4月1日期间的开发工作，包括任务类型重构、参数传递方案设计、性能优化和问题修复。

---

## 一、调度中心任务类型重构

### 1.1 背景

原有调度中心支持的任务类型：
- `redis_cache`: Redis缓存任务
- `dashboard_task`: Dashboard2任务
- `python_script`: Python脚本执行
- `chain`: 调度链

**问题**：参数传递方式不统一，缺乏灵活性

### 1.2 新设计

重构为三种统一的任务类型：

| 类型 | 标识 | 执行方式 | 适用场景 |
|-----|------|---------|---------|
| **function** | `function` | 直接调用Python函数 | 轻量级任务（缓存更新、数据清理） |
| **script** | `script` | 启动独立Python进程 | 耗时任务（数据采集、分析） |
| **scheduler** | `scheduler` | 调用Dashboard2现有调度器 | 复用采集/分析模块 |

### 1.3 统一参数传递方案

#### 参数定义规范

```python
PARAM_SCHEMA = {
    "param_name": {
        "type": "string|int|float|bool|date|select|list",
        "required": True|False,
        "default": value,
        "description": "参数说明",
        "options": [...],        # select类型选项
        "min": min_value,        # int/float最小值
        "max": max_value,        # int/float最大值
    }
}
```

#### 参数传递方式

| 任务类型 | 参数传递方式 | 环境变量格式 |
|---------|-------------|-------------|
| function | 函数参数直接传递 | 不适用 |
| script | 环境变量 | `gs2026_{script_name}_{param_name}` |
| scheduler | 包装脚本参数 | 不适用 |

### 1.4 实施文件

- `src/gs2026/dashboard2/services/scheduler_service.py` - 调度服务核心
- `src/gs2026/dashboard2/routes/scheduler.py` - API路由
- `docs/scheduler_task_types_design.md` - 设计方案文档

### 1.5 Git提交

- `0e4e813` - feat: implement three task types (function/script/scheduler)

---

## 二、combine_ztb_area.py 参数传递方案

### 2.1 需求

用户要求：
- 仅修改 `base_date` 参数从前端传递到后台
- 其他参数保持硬编码
- 最大限度减少代码修改

### 2.2 实现方案

选择**环境变量方案**（方案A）：

```python
# 读取环境变量
date_str = os.environ.get('gs2026_combine_ztb_area_date')
if date_str:
    base_date = datetime.strptime(date_str, '%Y%m%d')
else:
    base_date = datetime(2026, 3, 30)  # 默认日期
```

### 2.3 修改内容

```python
# combine_ztb_area.py
if __name__ == "__main__":
    # 从环境变量读取日期参数
    date_str = os.environ.get('gs2026_combine_ztb_area_date')
    if date_str:
        base_date = datetime.strptime(date_str, '%Y%m%d')
    else:
        base_date = datetime(2026, 3, 30)
    
    run_daemon_task(target=main_collection_pipeline, args=(base_date,))
```

### 2.4 相关文档

- `docs/scheduler_task_types_design.md` - 完整参数传递方案

---

## 三、性能优化

### 3.1 股票上攻排行API优化

#### 优化前问题
- 响应时间：27秒
- Redis查询：60次单独查询
- change_pct计算：逐只处理

#### 优化措施

| 优化项 | 实现方案 | 效果 |
|-------|---------|------|
| 批量查询 | Redis Pipeline 60次→1次 | 减少网络往返 |
| 向量化计算 | pandas向量化处理 | 10倍加速 |
| Redis Set | O(1)红名单查询 | 消除遍历 |
| 数据库索引 | 7个监控表添加索引 | 查询50-100ms |

#### 优化结果
- 响应时间：27秒 → 2.1秒（约13倍提升）

### 3.2 慢日志存储系统

#### 实现内容

| 组件 | 文件路径 |
|-----|---------|
| 数据表 | `slow_requests`, `slow_queries`, `slow_frontend_resources` |
| 数据模型 | `src/gs2026/dashboard2/models/slow_log.py` |
| 存储服务 | `src/gs2026/dashboard2/services/slow_log_storage.py` |
| API路由 | `src/gs2026/dashboard2/routes/performance.py` |
| 前端页面 | `templates/performance.html` |

#### 配置迁移

性能监控配置从环境变量迁移到 `configs/settings.yaml`：

```yaml
performance_monitor:
  enabled: false
  slow_threshold_ms: 1000

db_profiler:
  enabled: false
  slow_query_threshold_ms: 100

frontend_perf:
  enabled: false
  resource_timing: true
```

---

## 四、问题修复

### 4.1 调度中心时区显示

#### 问题
执行记录时间显示为GMT格式：`Tue, 31 Mar 2026 22:46:09 GMT`

#### 修复
添加 `_format_datetime()` 函数，统一返回 `+08:00` 格式：

```python
def _format_datetime(dt):
    """将datetime格式化为带时区的ISO格式（北京时间）"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    return dt
```

#### Git提交
- `37615e1` - fix: format datetime for execution detail and running executions
- `e11c945` - fix: display scheduler time in Beijing timezone

### 4.2 红名单缓存任务修复

#### 问题列表

| 问题 | 现象 | 修复方案 |
|-----|------|---------|
| 参数名不匹配 | `date` vs `date_str` | 自动转换参数名 |
| 日期格式错误 | `2026-03-31` vs `20260331` | 自动格式转换 |
| MySQL连接池 | 使用 `redis_util.con` | 改用 `mysql_tool.engine` |

#### Git提交
- `ff1b55b` - fix: convert 'date' param to 'date_str'
- `48ddd46` - fix: convert date format from YYYY-MM-DD to YYYYMMDD
- `c679a41` - fix: use mysql_tool.engine

### 4.3 股票-债券-行业映射缓存修复

#### 问题
- 缓存生成时间早于映射修复，导致部分股票缺少bond_code
- 示例：300992 应显示债券代码 123160，但缓存为空

#### 修复
强制更新Redis缓存：
- 缓存股票数：345只（原为295只）
- 300992 现在正确显示 `bond_code: '123160'`

### 4.4 DROP TABLE 卡顿问题

#### 现象
`drop_mysql_table('data_bond_daily')` 执行时卡顿

#### 根因
```
ID=37683, TIME=47964s(13.3小时)
  INFO=SELECT bond_code, close as bond_price...

ID=42375, TIME=1353s, STATE=Waiting for table metadata lock
  INFO=DROP TABLE data_bond_daily
```

长时间查询占用了metadata lock

#### 解决
终止长时间查询后，DROP TABLE 正常执行（0.10秒）

---

## 五、MySQL长时间查询监控脚本

### 5.1 功能

- 监控运行时间超过阈值的MySQL查询
- 自动终止长时间运行的查询（可配置）
- 跳过系统进程（ID<10或system user）
- 支持白名单和排除模式

### 5.2 文件

- `src/gs2026/collection/maintenance/mysql_long_query_monitor.py`
- `configs/scheduler_jobs/mysql_long_query_monitor.json`

### 5.3 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `gs2026_mysql_long_query_monitor_threshold` | 时间阈值(秒) | 600 |
| `gs2026_mysql_long_query_monitor_whitelist` | 白名单进程ID | "" |
| `gs2026_mysql_long_query_monitor_dry_run` | 仅监控不终止 | false |

### 5.4 Git提交

- `0119f68` - feat: add MySQL long query monitor
- `8611b94` - fix: skip system processes

---

## 六、Git提交汇总

| 提交 | 说明 | 时间 |
|------|------|------|
| `0e4e813` | feat: implement three task types | 03-31 |
| `ff1b55b` | fix: convert 'date' param to 'date_str' | 03-31 |
| `48ddd46` | fix: convert date format | 03-31 |
| `c679a41` | fix: use mysql_tool.engine | 03-31 |
| `e11c945` | fix: display scheduler time in Beijing timezone | 03-31 |
| `37615e1` | fix: format datetime for execution detail | 03-31 |
| `84e4a94` | perf: batch stock mapping query | 03-31 |
| `bc27fb6` | perf: vectorized change_pct | 03-31 |
| `17ba5d2` | perf: Redis Set for red list | 03-31 |
| `22bdd29` | perf: simplified change_pct batch query | 03-31 |
| `0119f68` | feat: add MySQL long query monitor | 04-01 |
| `8611b94` | fix: skip system processes | 04-01 |

---

## 七、待办事项

### 已完成
- [x] 调度中心任务类型重构设计
- [x] combine_ztb_area.py 参数传递
- [x] 性能监控配置迁移
- [x] 慢日志存储系统
- [x] 时区显示修复
- [x] 红名单缓存任务修复
- [x] MySQL长时间查询监控

### 待完成
- [ ] 前端参数表单动态生成
- [ ] 在调度中心导入MySQL监控任务
- [ ] 测试script类型任务执行
- [ ] 可转债采集优化（并发/批量）

---

## 八、相关文档

| 文档 | 路径 |
|-----|------|
| 调度中心任务类型设计 | `docs/scheduler_task_types_design.md` |
| 债券采集优化方案 | `docs/bond_collection_optimization.md` |
| 性能分析设计 | `docs/performance_analysis_design.md` |
| 慢日志存储设计 | `docs/slow_log_storage_design.md` |
| 开发总结 | `docs/development_summary_2026-03-31_to_2026-04-01.md` |

---

*文档生成时间：2026-04-01 01:25*
