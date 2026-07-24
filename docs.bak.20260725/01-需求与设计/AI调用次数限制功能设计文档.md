# AI调用次数限制功能 - 设计文档

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
