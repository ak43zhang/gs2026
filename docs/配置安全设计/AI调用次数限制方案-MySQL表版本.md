# AI调用次数限制方案 - MySQL表版本

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
