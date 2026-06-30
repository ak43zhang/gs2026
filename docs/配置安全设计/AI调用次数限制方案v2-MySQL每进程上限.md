# AI调用次数限制方案 v2 - MySQL表版本

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
