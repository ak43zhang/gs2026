# AI调用次数限制 - 集成方案

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
