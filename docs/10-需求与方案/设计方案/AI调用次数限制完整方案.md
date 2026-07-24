# AI调用次数限制完整方案

---

## 版本沿革

| 版本 | 日期 | 说明 |
|------|------|------|
| AI调用次数限制-集成方案 | 2026-06-30 | 历史版本 |
| AI调用次数限制-集成方案 | 2026-06-30 | 历史版本 |
| AI调用次数限制功能设计文档 | 2026-06-30 | 历史版本 |
| AI调用次数限制功能设计文档 | 2026-06-30 | 历史版本 |
| AI调用次数限制方案v2-MySQL每进程上限 | 2026-06-30 | 历史版本 |
| AI调用次数限制方案-MySQL表版本 | 2026-06-30 | 历史版本 |

**当前版本**：AI调用次数限制完整方案  
**状态**：🔵 已实施  
**最后更新**：2026-07-25

---

## 1. AI调用次数限制-集成方案


## 一、当前已集成

| 文件 | 进程名 | 上限 | 状态 |
|------|--------|------|------|
| `deepseek_analysis_news_combine.py` | `deepseek_news_combine` | 50 | ✅ 已集成 |

## 二、本次需集成（DeepSeek版）

### 2.1 deepseek_analysis_news_cls.py

**结构**：与 combine 完全一致
- `deepseek_ai()` → AI调用点（第170行附近）
- `time_task_do_cls()` → 主循环（while True）
- `__main__` → `run_daemon_task(target=time_task_do_cls, ...)`

**集成方式**（与combine一致）：
1. 在 `deepseek_ai()` 中调用AI前加 `check_and_increment("deepseek_news_cls")`
2. 新增 `time_task_do_cls_with_limit()` 包装函数
3. `__main__` 改为调用 `time_task_do_cls_with_limit`
4. 进程名：`deepseek_news_cls`，上限：50次

### 2.2 deepseek_analysis_notice.py

**结构**：略有不同
- `deepseek_ai()` → AI调用点（第183行附近）
- `timer_task_do_notice()` → 主循环（while True，但无数据时自动break）
- `__main__` → `run_daemon_task(target=timer_task_do_notice, ..., daemon=False)`

**集成方式**：
1. 在 `deepseek_ai()` 中调用AI前加 `check_and_increment("deepseek_notice")`
2. 新增 `timer_task_do_notice_with_limit()` 包装函数
3. `__main__` 改为调用 `timer_task_do_notice_with_limit`
4. 进程名：`deepseek_notice`，上限：50次

## 三、火山方舟迁移分析

### 3.1 火山方舟独立运行模式

每个火山方舟分析文件可以独立运行，结构与DeepSeek版一致：

| 文件 | AI调用点 | 主循环 | 进程名 |
|------|---------|--------|--------|
| `volcengine_analysis_news_cls.py` | `volcengine_ai()` L133 | `time_task_do_cls()` | `volcengine_news_cls` |
| `volcengine_analysis_news_combine.py` | `volcengine_ai()` L96 | `time_task_do_combine()` | `volcengine_news_combine` |
| `volcengine_analysis_news_ztb.py` | `volcengine_ai()` L40 | `time_task_do_ztb()` | `volcengine_news_ztb` |
| `volcengine_analysis_notice.py` | `volcengine_ai()` L90 | 无独立主循环 | `volcengine_notice` |
| `volcengine_analysis_event_driven.py` | `area_ai_analysis()` | 无独立主循环 | `volcengine_event_driven` |

**集成方式**（与DeepSeek一致）：
1. 在各 `volcengine_ai()` 函数调用API前加 `check_and_increment(进程名)`
2. 独立运行时：新增 `_with_limit` 包装函数
3. 通过调度器运行时：由调度器统一管理（见3.2）

### 3.2 volcengine_scheduler.py 调度器模式

**当前结构**：
```python
TASKS = [
    ("news_ztb", _run_ztb),
    # ("news_cls", _run_cls),
    # ("news_combine", _run_combine),
    # ("notice", _run_notice),
]

def run_scheduler():
    while True:
        for task_name, task_func in TASKS:
            task_func()  # 执行任务
        time.sleep(IDLE_WAIT)
```

**调度器集成方案**：

调度器**不需要**在外层做限制！因为：
- 每个 `_run_xxx()` 内部调用了对应的 `volcengine_ai()`
- `volcengine_ai()` 内部已有 `check_and_increment()` 检查
- 达到上限后 `volcengine_ai()` 直接return，不消耗API

**但需要让调度器知道何时退出**：

新增 `run_scheduler_with_limit()` 包装器：
```python
def run_scheduler_with_limit():
    """带调用次数限制的调度器"""
    from gs2026.utils.ai_call_counter import get_status
    
    while True:
        # 检查所有任务是否都已耗尽
        all_exhausted = True
        for task_name, _ in TASKS:
            status = get_status(f"volcengine_{task_name}")
            if status["status"] != "已耗尽":
                all_exhausted = False
                break
        
        if all_exhausted:
            logger.info("[调度器] 所有任务已达每日上限，优雅退出")
            break
        
        # 正常调度（内部volcengine_ai会检查单任务限制）
        for task_name, task_func in TASKS:
            task_func()
            time.sleep(TASK_GAP)
        
        time.sleep(IDLE_WAIT)
```

### 3.3 火山方舟进程名与上限配置

```sql
INSERT INTO ai_call_limit (process_name, max_calls, description) VALUES
    ('volcengine_news_cls', 50, '火山方舟-财联社新闻分析'),
    ('volcengine_news_combine', 50, '火山方舟-综合新闻分析'),
    ('volcengine_news_ztb', 50, '火山方舟-涨停板分析'),
    ('volcengine_notice', 50, '火山方舟-公告分析'),
    ('volcengine_event_driven', 50, '火山方舟-事件驱动分析')
ON DUPLICATE KEY UPDATE max_calls = VALUES(max_calls);
```

## 四、实施步骤

### Phase 1（本次实施）
1. 集成到 `deepseek_analysis_news_cls.py`
2. 集成到 `deepseek_analysis_notice.py`
3. 创建MySQL配置数据

### Phase 2（测试通过后）
4. 集成到 `volcengine_analysis_news_cls.py`
5. 集成到 `volcengine_analysis_news_combine.py`
6. 集成到 `volcengine_analysis_news_ztb.py`
7. 集成到 `volcengine_analysis_notice.py`
8. 集成到 `volcengine_analysis_event_driven.py`
9. 新增 `run_scheduler_with_limit()` 到 `volcengine_scheduler.py`

## 五、非嵌入式保证

**移除限制只需**：
- 独立运行的文件：`__main__` 中 `_with_limit` 改回原版函数名
- 调度器：`__main__` 中 `run_scheduler_with_limit` 改回 `run_scheduler`
- `volcengine_ai()` / `deepseek_ai()` 中删除3行 `check_and_increment`

**原有函数完全不改**：`get_news_cls_analysis`, `time_task_do_cls` 等保持原样。


---

## 2. AI调用次数限制-集成方案


## 一、当前已集成

| 文件 | 进程名 | 上限 | 状态 |
|------|--------|------|------|
| `deepseek_analysis_news_combine.py` | `deepseek_news_combine` | 50 | ✅ 已集成 |

## 二、本次需集成（DeepSeek版）

### 2.1 deepseek_analysis_news_cls.py

**结构**：与 combine 完全一致
- `deepseek_ai()` → AI调用点（第170行附近）
- `time_task_do_cls()` → 主循环（while True）
- `__main__` → `run_daemon_task(target=time_task_do_cls, ...)`

**集成方式**（与combine一致）：
1. 在 `deepseek_ai()` 中调用AI前加 `check_and_increment("deepseek_news_cls")`
2. 新增 `time_task_do_cls_with_limit()` 包装函数
3. `__main__` 改为调用 `time_task_do_cls_with_limit`
4. 进程名：`deepseek_news_cls`，上限：50次

### 2.2 deepseek_analysis_notice.py

**结构**：略有不同
- `deepseek_ai()` → AI调用点（第183行附近）
- `timer_task_do_notice()` → 主循环（while True，但无数据时自动break）
- `__main__` → `run_daemon_task(target=timer_task_do_notice, ..., daemon=False)`

**集成方式**：
1. 在 `deepseek_ai()` 中调用AI前加 `check_and_increment("deepseek_notice")`
2. 新增 `timer_task_do_notice_with_limit()` 包装函数
3. `__main__` 改为调用 `timer_task_do_notice_with_limit`
4. 进程名：`deepseek_notice`，上限：50次

## 三、火山方舟迁移分析

### 3.1 火山方舟独立运行模式

每个火山方舟分析文件可以独立运行，结构与DeepSeek版一致：

| 文件 | AI调用点 | 主循环 | 进程名 |
|------|---------|--------|--------|
| `volcengine_analysis_news_cls.py` | `volcengine_ai()` L133 | `time_task_do_cls()` | `volcengine_news_cls` |
| `volcengine_analysis_news_combine.py` | `volcengine_ai()` L96 | `time_task_do_combine()` | `volcengine_news_combine` |
| `volcengine_analysis_news_ztb.py` | `volcengine_ai()` L40 | `time_task_do_ztb()` | `volcengine_news_ztb` |
| `volcengine_analysis_notice.py` | `volcengine_ai()` L90 | 无独立主循环 | `volcengine_notice` |
| `volcengine_analysis_event_driven.py` | `area_ai_analysis()` | 无独立主循环 | `volcengine_event_driven` |

**集成方式**（与DeepSeek一致）：
1. 在各 `volcengine_ai()` 函数调用API前加 `check_and_increment(进程名)`
2. 独立运行时：新增 `_with_limit` 包装函数
3. 通过调度器运行时：由调度器统一管理（见3.2）

### 3.2 volcengine_scheduler.py 调度器模式

**当前结构**：
```python
TASKS = [
    ("news_ztb", _run_ztb),
    # ("news_cls", _run_cls),
    # ("news_combine", _run_combine),
    # ("notice", _run_notice),
]

def run_scheduler():
    while True:
        for task_name, task_func in TASKS:
            task_func()  # 执行任务
        time.sleep(IDLE_WAIT)
```

**调度器集成方案**：

调度器**不需要**在外层做限制！因为：
- 每个 `_run_xxx()` 内部调用了对应的 `volcengine_ai()`
- `volcengine_ai()` 内部已有 `check_and_increment()` 检查
- 达到上限后 `volcengine_ai()` 直接return，不消耗API

**但需要让调度器知道何时退出**：

新增 `run_scheduler_with_limit()` 包装器：
```python
def run_scheduler_with_limit():
    """带调用次数限制的调度器"""
    from gs2026.utils.ai_call_counter import get_status
    
    while True:
        # 检查所有任务是否都已耗尽
        all_exhausted = True
        for task_name, _ in TASKS:
            status = get_status(f"volcengine_{task_name}")
            if status["status"] != "已耗尽":
                all_exhausted = False
                break
        
        if all_exhausted:
            logger.info("[调度器] 所有任务已达每日上限，优雅退出")
            break
        
        # 正常调度（内部volcengine_ai会检查单任务限制）
        for task_name, task_func in TASKS:
            task_func()
            time.sleep(TASK_GAP)
        
        time.sleep(IDLE_WAIT)
```

### 3.3 火山方舟进程名与上限配置

```sql
INSERT INTO ai_call_limit (process_name, max_calls, description) VALUES
    ('volcengine_news_cls', 50, '火山方舟-财联社新闻分析'),
    ('volcengine_news_combine', 50, '火山方舟-综合新闻分析'),
    ('volcengine_news_ztb', 50, '火山方舟-涨停板分析'),
    ('volcengine_notice', 50, '火山方舟-公告分析'),
    ('volcengine_event_driven', 50, '火山方舟-事件驱动分析')
ON DUPLICATE KEY UPDATE max_calls = VALUES(max_calls);
```

## 四、实施步骤

### Phase 1（本次实施）
1. 集成到 `deepseek_analysis_news_cls.py`
2. 集成到 `deepseek_analysis_notice.py`
3. 创建MySQL配置数据

### Phase 2（测试通过后）
4. 集成到 `volcengine_analysis_news_cls.py`
5. 集成到 `volcengine_analysis_news_combine.py`
6. 集成到 `volcengine_analysis_news_ztb.py`
7. 集成到 `volcengine_analysis_notice.py`
8. 集成到 `volcengine_analysis_event_driven.py`
9. 新增 `run_scheduler_with_limit()` 到 `volcengine_scheduler.py`

## 五、非嵌入式保证

**移除限制只需**：
- 独立运行的文件：`__main__` 中 `_with_limit` 改回原版函数名
- 调度器：`__main__` 中 `run_scheduler_with_limit` 改回 `run_scheduler`
- `volcengine_ai()` / `deepseek_ai()` 中删除3行 `check_and_increment`

**原有函数完全不改**：`get_news_cls_analysis`, `time_task_do_cls` 等保持原样。


---

## 3. AI调用次数限制功能设计文档


## 一、功能概述

为所有AI分析进程提供**每日调用次数限制**，防止AI API调用过多造成费用浪费。

### 核心特性

- **非嵌入式设计**：增加/删除功能方便，不影响原有业务逻辑
- **每进程独立上限**：领域分析100次、新闻分析100次等
- **MySQL持久化**：跨进程/跨机器共享，支持并发
- **优雅停止**：达到上限后进程正常退出，不崩溃
- **每日自动重置**：按日期隔离，无需手动清理

## 二、数据库设计

### 表1：ai_call_limit（上限配置表）

```sql
CREATE TABLE IF NOT EXISTS `ai_call_limit` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL UNIQUE COMMENT '进程名（唯一标识）',
    `max_calls` INT DEFAULT 0 COMMENT '每日最大调用次数（0=永久不限制）',
    `enabled` TINYINT DEFAULT 1 COMMENT '是否启用限制（1=启用，0=禁用）',
    `description` VARCHAR(128) COMMENT '进程描述',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数上限配置';
```

### 表2：ai_call_counter（调用计数表）

```sql
CREATE TABLE IF NOT EXISTS `ai_call_counter` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL COMMENT '进程名',
    `call_date` DATE NOT NULL COMMENT '调用日期',
    `call_count` INT DEFAULT 0 COMMENT '当日已调用次数',
    `last_call_time` DATETIME COMMENT '最后一次调用时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_process_date` (`process_name`, `call_date`),
    KEY `idx_call_date` (`call_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数计数表';
```

### 初始化配置数据

```sql
INSERT INTO ai_call_limit (process_name, max_calls, description) VALUES
    ('anomaly_analyzer', 100, '盘中异动AI分析'),
    ('scheduler_news_ztb', 100, '涨停板新闻分析'),
    ('scheduler_news_cls', 100, '财联社新闻分析'),
    ('scheduler_news_combine', 100, '综合新闻分析'),
    ('scheduler_notice', 100, '公告分析'),
    ('scheduler_event_driven', 100, '事件驱动分析')
ON DUPLICATE KEY UPDATE max_calls = VALUES(max_calls);
```

## 三、模块设计

### 文件位置

```
src/gs2026/utils/ai_call_counter.py
```

### 核心API

```python
def check_and_increment(process_name: str) -> bool:
    """
    检查并增加调用计数（AI调用前必须调用此函数）
    
    Args:
        process_name: 进程名（对应ai_call_limit表的process_name）
    
    Returns:
        True: 可以继续调用AI
        False: 已达到上限，需要停止
    
    特殊情况：
        - ai_call_limit表中无此进程配置：永久模式，直接通过
        - max_calls=0：永久模式，直接通过
        - enabled=0：限制禁用，直接通过
        - 数据库异常：降级放行，记录警告日志
    """

def get_status(process_name: str = None) -> dict:
    """获取进程调用状态"""

def set_limit(process_name: str, max_calls: int, description: str = ''):
    """设置指定进程的上限"""

def reset_counter(process_name: str = None):
    """重置指定进程今日的计数器"""
```

### 核心逻辑流程

```
check_and_increment("anomaly_analyzer")
    │
    ├─ 1. 查询 ai_call_limit 表获取配置
    │     → 无记录 / max_calls=0 / enabled=0 → return True（放行）
    │
    ├─ 2. 原子操作增加计数器
    │     INSERT INTO ai_call_counter ... ON DUPLICATE KEY UPDATE call_count+1
    │
    ├─ 3. 检查是否超过上限
    │     → call_count > max_calls → return False（拒绝）
    │     → call_count >= max_calls*0.9 → 打印警告日志
    │     → 正常 → return True（放行）
    │
    └─ 异常处理
          → 数据库连接失败 → return True（降级放行）
```

## 四、接入方式（非嵌入式）

### 接入（一行代码）

在任何AI调用点前加入：

```python
from gs2026.utils.ai_call_counter import check_and_increment

# 在_call_ai()函数开头
if not check_and_increment("anomaly_analyzer"):
    logger.warning("[异动分析] AI调用次数已达上限")
    return None
```

### 移除（一行代码）

删除上述 `if not check_and_increment(...)` 判断即可，不影响任何原有逻辑。

### 非嵌入式保证

1. `ai_call_counter.py` 是独立模块，不依赖业务代码
2. 接入点是**前置检查**，不修改原有函数签名和逻辑
3. 删除检查代码后，所有AI调用恢复正常
4. MySQL表存在与否不影响业务（异常降级放行）

## 五、集成清单

| 文件 | 集成位置 | 进程名 |
|------|---------|--------|
| `anomaly_analyzer.py` | `_call_ai()` 函数开头 | `anomaly_analyzer` |
| `volcengine_scheduler.py` | 每个任务执行前 | `scheduler_{task_name}` |
| `volcengine_analysis_news_cls.py` | 分析函数入口 | `scheduler_news_cls` |
| `volcengine_analysis_news_combine.py` | 分析函数入口 | `scheduler_news_combine` |
| `volcengine_analysis_news_ztb.py` | 分析函数入口 | `scheduler_news_ztb` |
| `volcengine_analysis_notice.py` | 分析函数入口 | `scheduler_notice` |
| `volcengine_analysis_event_driven.py` | 分析函数入口 | `scheduler_event_driven` |

## 六、管理操作

### 查看今日调用情况

```sql
SELECT 
    l.process_name,
    l.description,
    COALESCE(c.call_count, 0) as call_count,
    l.max_calls,
    CASE WHEN l.max_calls = 0 THEN '永久'
         WHEN COALESCE(c.call_count, 0) >= l.max_calls THEN '已耗尽'
         WHEN COALESCE(c.call_count, 0) >= l.max_calls * 0.9 THEN '即将耗尽'
         ELSE '正常' END as status,
    c.last_call_time
FROM ai_call_limit l
LEFT JOIN ai_call_counter c ON l.process_name = c.process_name AND c.call_date = CURDATE()
ORDER BY COALESCE(c.call_count, 0) DESC;
```

### 修改上限

```sql
UPDATE ai_call_limit SET max_calls = 200 WHERE process_name = 'anomaly_analyzer';
```

### 临时禁用某进程的限制

```sql
UPDATE ai_call_limit SET enabled = 0 WHERE process_name = 'anomaly_analyzer';
```

### 设为永久不限制

```sql
UPDATE ai_call_limit SET max_calls = 0 WHERE process_name = 'anomaly_analyzer';
```

### 重置今日计数

```sql
DELETE FROM ai_call_counter WHERE process_name = 'anomaly_analyzer' AND call_date = CURDATE();
```

## 七、实施步骤

1. 提交当前代码作为回退点
2. 创建MySQL表（`ai_call_limit` + `ai_call_counter`）
3. 插入初始配置数据
4. 创建 `src/gs2026/utils/ai_call_counter.py` 模块
5. 集成到 `anomaly_analyzer.py`
6. 集成到 `volcengine_scheduler.py`
7. 集成到其他AI分析模块
8. 测试验证
9. 提交代码

## 八、回退方案

如需回退：
1. 删除各集成点的 `check_and_increment()` 调用
2. 删除 `ai_call_counter.py` 文件
3. MySQL表可保留或删除（不影响业务）


---

## 4. AI调用次数限制功能设计文档


## 一、功能概述

为所有AI分析进程提供**每日调用次数限制**，防止AI API调用过多造成费用浪费。

### 核心特性

- **非嵌入式设计**：增加/删除功能方便，不影响原有业务逻辑
- **每进程独立上限**：领域分析100次、新闻分析100次等
- **MySQL持久化**：跨进程/跨机器共享，支持并发
- **优雅停止**：达到上限后进程正常退出，不崩溃
- **每日自动重置**：按日期隔离，无需手动清理

## 二、数据库设计

### 表1：ai_call_limit（上限配置表）

```sql
CREATE TABLE IF NOT EXISTS `ai_call_limit` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL UNIQUE COMMENT '进程名（唯一标识）',
    `max_calls` INT DEFAULT 0 COMMENT '每日最大调用次数（0=永久不限制）',
    `enabled` TINYINT DEFAULT 1 COMMENT '是否启用限制（1=启用，0=禁用）',
    `description` VARCHAR(128) COMMENT '进程描述',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数上限配置';
```

### 表2：ai_call_counter（调用计数表）

```sql
CREATE TABLE IF NOT EXISTS `ai_call_counter` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL COMMENT '进程名',
    `call_date` DATE NOT NULL COMMENT '调用日期',
    `call_count` INT DEFAULT 0 COMMENT '当日已调用次数',
    `last_call_time` DATETIME COMMENT '最后一次调用时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_process_date` (`process_name`, `call_date`),
    KEY `idx_call_date` (`call_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数计数表';
```

### 初始化配置数据

```sql
INSERT INTO ai_call_limit (process_name, max_calls, description) VALUES
    ('anomaly_analyzer', 100, '盘中异动AI分析'),
    ('scheduler_news_ztb', 100, '涨停板新闻分析'),
    ('scheduler_news_cls', 100, '财联社新闻分析'),
    ('scheduler_news_combine', 100, '综合新闻分析'),
    ('scheduler_notice', 100, '公告分析'),
    ('scheduler_event_driven', 100, '事件驱动分析')
ON DUPLICATE KEY UPDATE max_calls = VALUES(max_calls);
```

## 三、模块设计

### 文件位置

```
src/gs2026/utils/ai_call_counter.py
```

### 核心API

```python
def check_and_increment(process_name: str) -> bool:
    """
    检查并增加调用计数（AI调用前必须调用此函数）
    
    Args:
        process_name: 进程名（对应ai_call_limit表的process_name）
    
    Returns:
        True: 可以继续调用AI
        False: 已达到上限，需要停止
    
    特殊情况：
        - ai_call_limit表中无此进程配置：永久模式，直接通过
        - max_calls=0：永久模式，直接通过
        - enabled=0：限制禁用，直接通过
        - 数据库异常：降级放行，记录警告日志
    """

def get_status(process_name: str = None) -> dict:
    """获取进程调用状态"""

def set_limit(process_name: str, max_calls: int, description: str = ''):
    """设置指定进程的上限"""

def reset_counter(process_name: str = None):
    """重置指定进程今日的计数器"""
```

### 核心逻辑流程

```
check_and_increment("anomaly_analyzer")
    │
    ├─ 1. 查询 ai_call_limit 表获取配置
    │     → 无记录 / max_calls=0 / enabled=0 → return True（放行）
    │
    ├─ 2. 原子操作增加计数器
    │     INSERT INTO ai_call_counter ... ON DUPLICATE KEY UPDATE call_count+1
    │
    ├─ 3. 检查是否超过上限
    │     → call_count > max_calls → return False（拒绝）
    │     → call_count >= max_calls*0.9 → 打印警告日志
    │     → 正常 → return True（放行）
    │
    └─ 异常处理
          → 数据库连接失败 → return True（降级放行）
```

## 四、接入方式（非嵌入式）

### 接入（一行代码）

在任何AI调用点前加入：

```python
from gs2026.utils.ai_call_counter import check_and_increment

# 在_call_ai()函数开头
if not check_and_increment("anomaly_analyzer"):
    logger.warning("[异动分析] AI调用次数已达上限")
    return None
```

### 移除（一行代码）

删除上述 `if not check_and_increment(...)` 判断即可，不影响任何原有逻辑。

### 非嵌入式保证

1. `ai_call_counter.py` 是独立模块，不依赖业务代码
2. 接入点是**前置检查**，不修改原有函数签名和逻辑
3. 删除检查代码后，所有AI调用恢复正常
4. MySQL表存在与否不影响业务（异常降级放行）

## 五、集成清单

| 文件 | 集成位置 | 进程名 |
|------|---------|--------|
| `anomaly_analyzer.py` | `_call_ai()` 函数开头 | `anomaly_analyzer` |
| `volcengine_scheduler.py` | 每个任务执行前 | `scheduler_{task_name}` |
| `volcengine_analysis_news_cls.py` | 分析函数入口 | `scheduler_news_cls` |
| `volcengine_analysis_news_combine.py` | 分析函数入口 | `scheduler_news_combine` |
| `volcengine_analysis_news_ztb.py` | 分析函数入口 | `scheduler_news_ztb` |
| `volcengine_analysis_notice.py` | 分析函数入口 | `scheduler_notice` |
| `volcengine_analysis_event_driven.py` | 分析函数入口 | `scheduler_event_driven` |

## 六、管理操作

### 查看今日调用情况

```sql
SELECT 
    l.process_name,
    l.description,
    COALESCE(c.call_count, 0) as call_count,
    l.max_calls,
    CASE WHEN l.max_calls = 0 THEN '永久'
         WHEN COALESCE(c.call_count, 0) >= l.max_calls THEN '已耗尽'
         WHEN COALESCE(c.call_count, 0) >= l.max_calls * 0.9 THEN '即将耗尽'
         ELSE '正常' END as status,
    c.last_call_time
FROM ai_call_limit l
LEFT JOIN ai_call_counter c ON l.process_name = c.process_name AND c.call_date = CURDATE()
ORDER BY COALESCE(c.call_count, 0) DESC;
```

### 修改上限

```sql
UPDATE ai_call_limit SET max_calls = 200 WHERE process_name = 'anomaly_analyzer';
```

### 临时禁用某进程的限制

```sql
UPDATE ai_call_limit SET enabled = 0 WHERE process_name = 'anomaly_analyzer';
```

### 设为永久不限制

```sql
UPDATE ai_call_limit SET max_calls = 0 WHERE process_name = 'anomaly_analyzer';
```

### 重置今日计数

```sql
DELETE FROM ai_call_counter WHERE process_name = 'anomaly_analyzer' AND call_date = CURDATE();
```

## 七、实施步骤

1. 提交当前代码作为回退点
2. 创建MySQL表（`ai_call_limit` + `ai_call_counter`）
3. 插入初始配置数据
4. 创建 `src/gs2026/utils/ai_call_counter.py` 模块
5. 集成到 `anomaly_analyzer.py`
6. 集成到 `volcengine_scheduler.py`
7. 集成到其他AI分析模块
8. 测试验证
9. 提交代码

## 八、回退方案

如需回退：
1. 删除各集成点的 `check_and_increment()` 调用
2. 删除 `ai_call_counter.py` 文件
3. MySQL表可保留或删除（不影响业务）


---

## 5. AI调用次数限制方案v2-MySQL每进程上限


## 背景

- 不同AI分析进程需要独立的每日调用上限
- 领域分析100次、新闻分析100次、公告分析100次等
- 所有进程共享同一个MySQL表，按进程名隔离

## 方案设计

### 1. MySQL表设计（两表方案）

#### 主表：ai_call_counter（计数器）
```sql
CREATE TABLE IF NOT EXISTS `ai_call_counter` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL COMMENT '进程名',
    `call_date` DATE NOT NULL COMMENT '调用日期',
    `call_count` INT DEFAULT 0 COMMENT '当日调用次数',
    `last_call_time` DATETIME COMMENT '最后一次调用时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_process_date` (`process_name`, `call_date`),
    KEY `idx_call_date` (`call_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数计数器';
```

#### 配置表：ai_call_limit（上限配置）
```sql
CREATE TABLE IF NOT EXISTS `ai_call_limit` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL UNIQUE COMMENT '进程名',
    `max_calls` INT DEFAULT 0 COMMENT '每日最大调用次数（0=永久）',
    `enabled` TINYINT DEFAULT 1 COMMENT '是否启用（1=启用，0=禁用）',
    `description` VARCHAR(128) COMMENT '描述',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数上限配置';
```

### 2. 核心逻辑

#### check_and_increment() 流程

```
1. 获取进程名（默认=当前脚本名）
2. 获取今天日期
3. 加锁（线程安全）
4. 查询 ai_call_limit 表：
   SELECT max_calls, enabled FROM ai_call_limit 
   WHERE process_name=?
5. 如果enabled=0：计数器功能禁用，直接通过
6. 如果没配置记录或max_calls=0：永久模式，直接通过
7. 查询 ai_call_counter 表：
   SELECT call_count FROM ai_call_counter 
   WHERE process_name=? AND call_date=?
8. 如果count >= max_calls：返回False（达到上限）
9. 否则：原子操作增加计数，返回True
10. 接近上限时（>=90%）打印警告日志
```

#### SQL原子操作

```sql
-- 增加计数器（原子操作）
INSERT INTO ai_call_counter (process_name, call_date, call_count, last_call_time)
VALUES ('anomaly_analyzer', '2026-06-30', 1, NOW())
ON DUPLICATE KEY UPDATE
    call_count = call_count + 1,
    last_call_time = NOW();
```

#### 检查是否达上限

```sql
-- 检查是否超过上限
SELECT c.call_count, l.max_calls, l.enabled
FROM ai_call_counter c
LEFT JOIN ai_call_limit l ON c.process_name = l.process_name
WHERE c.process_name = 'anomaly_analyzer' AND c.call_date = '2026-06-30';
```

### 3. 配置数据示例

```sql
-- 初始化配置
INSERT INTO ai_call_limit (process_name, max_calls, description) VALUES
    ('anomaly_analyzer', 100, '盘中异动AI分析'),
    ('scheduler_news_ztb', 100, '涨停板分析'),
    ('scheduler_news_cls', 100, '财联社新闻分析'),
    ('scheduler_news_combine', 100, '综合新闻分析'),
    ('scheduler_notice', 100, '公告分析'),
    ('scheduler_event_driven', 100, '事件驱动分析'),
    ('deepseek_analyzer', 100, 'DeepSeek分析'),
    ('baidu_analyzer', 100, '百度分析')
ON DUPLICATE KEY UPDATE max_calls = VALUES(max_calls);
```

### 4. 配置方式

#### 方式A：配置文件（默认读取MySQL表）

```yaml
# configs/settings.yaml
common:
  ai_call_limit_enabled: true  # 是否启用限制
```

#### 方式B：命令行参数（覆盖MySQL配置）

```bash
# 限制anomaly_analyzer为500次
python anomaly_analyzer.py --max-calls 500

# 永久（不限制）
python anomaly_analyzer.py --max-calls 0

# 禁用限制
python anomaly_analyzer.py --max-calls -1
```

#### 方式C：直接调用

```python
from gs2026.utils.ai_call_counter import check_and_increment

# 使用进程名自动匹配MySQL表中的上限
if not check_and_increment("anomaly_analyzer"):
    logger.warning("达到调用次数上限")
    return None

# 调用AI
result = _call_ai(prompt)
```

### 5. 工具模块API

```python
# src/gs2026/utils/ai_call_counter.py

class AICallCounter:
    """AI调用计数器（MySQL版本）"""
    
    @staticmethod
    def check_and_increment(process_name: str = None) -> bool:
        """
        检查并增加调用计数
        
        Args:
            process_name: 进程名（默认自动获取脚本名）
        
        Returns:
            True: 可以继续调用
            False: 已达到上限
        """
    
    @staticmethod
    def get_remaining(process_name: str = None) -> int:
        """获取剩余调用次数（-1=永久/未配置）"""
    
    @staticmethod
    def get_all_status() -> pd.DataFrame:
        """获取所有进程的调用状态（今日）"""
    
    @staticmethod
    def set_limit(process_name: str, max_calls: int, description: str = ''):
        """设置指定进程的上限（0=永久）"""
    
    @staticmethod
    def reset(process_name: str = None, call_date: str = None):
        """重置计数器"""
    
    @staticmethod
    def enable(process_name: str):
        """启用指定进程的限制"""
    
    @staticmethod
    def disable(process_name: str):
        """禁用指定进程的限制"""
```

### 6. 集成点

#### anomaly_analyzer.py

```python
def _call_ai(prompt: str) -> Optional[str]:
    """统一AI调用入口"""
    from gs2026.utils.ai_call_counter import check_and_increment
    if not check_and_increment("anomaly_analyzer"):
        logger.warning("[异动分析] AI调用次数已达上限，停止分析")
        global _should_exit
        _should_exit = True
        return None
    # 原有逻辑不变
```

#### volcengine_scheduler.py

```python
def run_scheduler():
    while True:
        for task_name, task_func in TASKS:
            if not check_and_increment(f"scheduler_{task_name}"):
                logger.info(f"[调度器] {task_name} 调用次数已达上限")
                # 不退出调度器，只跳过此任务
                continue
            task_func()
```

#### 其他AI分析模块

每个模块在调用AI前检查：
```python
from gs2026.utils.ai_call_counter import check_and_increment
if not check_and_increment("模块名"):
    return None
```

### 7. 管理功能

#### 查看所有进程状态

```python
from gs2026.utils.ai_call_counter import AICallCounter

# 获取所有进程今日调用情况
df = AICallCounter.get_all_status()
print(df)
# 输出：
# process_name          | call_count | max_calls | remaining | status
# anomaly_analyzer      | 45         | 100       | 55        | 正常
# scheduler_news_ztb    | 98         | 100       | 2         | 即将耗尽
# scheduler_news_cls    | 101        | 100       | 0         | 已耗尽
# deepseek_analyzer     | 0          | 0         | -1        | 永久
```

#### 修改上限

```python
# 动态调整
AICallCounter.set_limit("anomaly_analyzer", 200, "盘中异动AI分析")
AICallCounter.set_limit("deepseek_analyzer", 0, "取消限制")
AICallCounter.disable("baidu_analyzer")  # 临时禁用
```

#### 查询SQL

```sql
-- 今日各进程调用情况
SELECT 
    c.process_name,
    c.call_count,
    l.max_calls,
    CASE WHEN l.max_calls = 0 THEN '永久'
         WHEN c.call_count >= l.max_calls THEN '已耗尽'
         WHEN c.call_count >= l.max_calls * 0.9 THEN '即将耗尽'
         ELSE '正常' END as status,
    c.last_call_time
FROM ai_call_counter c
LEFT JOIN ai_call_limit l ON c.process_name = l.process_name
WHERE c.call_date = CURDATE()
ORDER BY c.call_count DESC;

-- 历史趋势
SELECT call_date, SUM(call_count) as total_calls
FROM ai_call_counter
WHERE call_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY call_date
ORDER BY call_date;
```

### 8. 安全特性

| 特性 | 说明 |
|------|------|
| 线程安全 | 使用文件锁+MySQL事务 |
| 进程隔离 | 每个进程独立计数 |
| 每日重置 | 新日期自动创建新记录 |
| 数据库异常降级 | 连接失败时允许通过，记录警告日志 |
| 防止绕过 | 计数器在AI调用前检查，非后置 |
| 全局上限 | 可设置全局总上限（可选） |

### 9. 可选扩展

#### 全局总上限

如需限制所有进程的合计上限，可增加：
```sql
-- 全局计数器
INSERT INTO ai_call_counter (process_name, call_date, call_count, ...)
VALUES ('__global__', '2026-06-30', 1, ...)
ON DUPLICATE KEY UPDATE call_count = call_count + 1;
```

### 10. 实施步骤

1. 创建MySQL表 `ai_call_counter` 和 `ai_call_limit`
2. 创建 `ai_call_counter.py` 工具模块
3. 初始化配置数据（INSERT INTO ai_call_limit）
4. 集成到 `anomaly_analyzer.py`（_call_ai入口）
5. 集成到 `volcengine_scheduler.py`（每任务前）
6. 集成到其他AI分析模块
7. 添加命令行参数 `--max-calls`
8. 测试验证


---

## 6. AI调用次数限制方案-MySQL表版本


## 背景

- 文件方案在多进程/多机器环境下存在并发问题
- MySQL表方案更可靠，支持事务、跨进程/跨机器共享
- 需要支持多个AI分析进程共享计数器

## 方案设计

### 1. MySQL表设计

```sql
CREATE TABLE IF NOT EXISTS `ai_call_counter` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `process_name` VARCHAR(64) NOT NULL COMMENT '进程名',
    `call_date` DATE NOT NULL COMMENT '调用日期',
    `call_count` INT DEFAULT 0 COMMENT '调用次数',
    `max_calls` INT DEFAULT 0 COMMENT '最大调用次数（0=永久）',
    `last_call_time` DATETIME COMMENT '最后一次调用时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_process_date` (`process_name`, `call_date`),
    KEY `idx_call_date` (`call_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用次数计数器';
```

### 2. 计数器模块设计

```python
# src/gs2026/utils/ai_call_counter.py

import threading
from datetime import date
from loguru import logger

_lock = threading.Lock()

def check_and_increment(process_name: str = None, max_calls: int = None) -> bool:
    """
    检查并增加调用计数（MySQL版本）
    
    Args:
        process_name: 进程名（默认自动获取）
        max_calls: 最大调用次数（None=使用表配置，0=永久）
    
    Returns:
        True: 可以继续调用
        False: 已达到上限，需要停止
    """
    ...

def get_remaining_calls(process_name: str = None) -> int:
    """获取剩余调用次数（-1=永久）"""
    ...

def set_max_calls(max_calls: int, process_name: str = None):
    """设置最大调用次数（0=永久）"""
    ...

def reset_counter(process_name: str = None, call_date: str = None):
    """手动重置计数器"""
    ...
```

### 3. 核心逻辑

#### check_and_increment() 流程

```
1. 获取进程名（默认=当前脚本名）
2. 获取今天日期
3. 加锁（线程安全）
4. 查询MySQL表：
   SELECT call_count, max_calls FROM ai_call_counter 
   WHERE process_name=? AND call_date=?
5. 如果不存在：INSERT新记录（count=0, max_calls=0）
6. 如果max_calls=0：永久模式，直接通过
7. 如果count >= max_calls：返回False（达到上限）
8. 否则：UPDATE count+1，返回True
9. 接近上限时（>=90%）打印警告日志
```

#### SQL实现（原子操作）

```sql
-- 检查并增加（原子操作，使用INSERT ... ON DUPLICATE KEY UPDATE）
INSERT INTO ai_call_counter (process_name, call_date, call_count, max_calls, last_call_time)
VALUES ('anomaly_analyzer', '2026-06-30', 1, 500, NOW())
ON DUPLICATE KEY UPDATE
    call_count = CASE 
        WHEN max_calls = 0 THEN call_count + 1  -- 永久模式
        WHEN call_count < max_calls THEN call_count + 1
        ELSE call_count  -- 已达上限，不增加
    END,
    last_call_time = NOW();
```

### 4. 配置方式

#### 方式A：配置文件（推荐）

```yaml
# configs/settings.yaml
common:
  ai_call_limit: 500        # 0=永久（默认）
  ai_call_limit_date: "2026-06-30"  # 生效日期
```

#### 方式B：命令行参数

```bash
# 限制500次
python anomaly_analyzer.py --max-calls 500

# 永久（不限制）
python anomaly_analyzer.py --max-calls 0
```

#### 方式C：环境变量

```bash
export AI_CALL_LIMIT=500
export AI_CALL_LIMIT_DATE=2026-06-30
```

### 5. 集成点

#### anomaly_analyzer.py

```python
def _call_ai(prompt: str) -> Optional[str]:
    """统一AI调用入口"""
    from gs2026.utils.ai_call_counter import check_and_increment
    if not check_and_increment("anomaly_analyzer"):
        logger.warning("[异动分析] AI调用次数已达上限，停止分析")
        global _should_exit
        _should_exit = True
        return None
    
    # 原有逻辑不变
    if AI_ENGINE == 'volcengine':
        ...
```

#### volcengine_scheduler.py

```python
def run_scheduler():
    round_num = 0
    while True:
        round_num += 1
        
        for task_name, task_func in TASKS:
            if not check_and_increment(f"scheduler_{task_name}"):
                logger.info("[调度器] AI调用次数已达上限，停止调度器")
                return
            # ... 原有逻辑
```

#### 其他AI模块

每个模块在调用AI前检查：

```python
from gs2026.utils.ai_call_counter import check_and_increment

if not check_and_increment("模块名"):
    logger.info("AI调用次数已达上限")
    return None
```

### 6. 管理功能

#### 查询当前状态

```sql
-- 查看所有进程的调用情况
SELECT process_name, call_date, call_count, max_calls,
       ROUND(call_count / max_calls * 100, 1) as usage_pct,
       last_call_time
FROM ai_call_counter
WHERE call_date = CURDATE()
ORDER BY call_count DESC;

-- 查看历史记录
SELECT process_name, call_date, call_count, max_calls, last_call_time
FROM ai_call_counter
WHERE call_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY call_date DESC, call_count DESC;
```

#### 修改限制

```python
from gs2026.utils.ai_call_counter import set_max_calls

# 设置为500次
set_max_calls(500)

# 设置为永久
set_max_calls(0)
```

#### 重置计数器

```python
from gs2026.utils.ai_call_counter import reset_counter

# 重置今天
reset_counter()

# 重置指定日期
reset_counter(call_date='2026-06-29')
```

### 7. 并发安全

| 场景 | 处理方式 |
|------|---------|
| 多进程同时调用 | MySQL唯一键约束保证原子性 |
| 进程崩溃 | 计数器已增加，下次启动时从MySQL恢复 |
| 网络中断 | 数据库连接异常时允许通过（不阻断业务） |
| 日期切换 | 自动识别新日期，创建新记录 |

### 8. 优势

1. **跨进程/跨机器共享**：所有AI分析进程共享MySQL表
2. **原子操作**：MySQL唯一键保证并发安全
3. **持久化**：数据不会丢失，可追溯历史
4. **可查询**：SQL查询调用记录，方便管理
5. **优雅退出**：达到上限后进程正常退出
6. **灵活配置**：支持配置文件、命令行、环境变量

### 9. 实施步骤

1. 创建MySQL表 `ai_call_counter`
2. 创建 `ai_call_counter.py` 工具模块
3. 集成到 `anomaly_analyzer.py`
4. 集成到 `volcengine_scheduler.py`
5. 集成到其他AI分析模块
6. 添加命令行参数 `--max-calls`
7. 测试验证

### 10. 注意事项

1. 数据库连接异常时，计数器功能降级（允许继续调用，记录日志）
2. 永久模式（max_calls=0）不限制，适合测试环境
3. 建议设置合理的上限，避免API费用超支
4. 定期清理历史记录（超过30天的记录可删除）


---

