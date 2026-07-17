# DeepSeek 账号每日使用次数限制

## 一、功能概述

每个 DeepSeek 账号每天限制使用次数（默认10次），达到限制后当天该账号不再分配，自动切换到下一个可用账号。所有账号达上限时跳过分析，等待次日自动重置。

## 二、数据库设计

### 2.1 accounts 表新增字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `daily_limit` | INT | 10 | 每日使用上限 |
| `today_used` | INT | 0 | 今日已使用次数 |
| `last_used_date` | DATE | NULL | 最后使用日期（用于跨天重置） |

### 2.2 DDL

```sql
ALTER TABLE accounts ADD COLUMN daily_limit INT DEFAULT 10 COMMENT '每日使用上限' AFTER use_count;
ALTER TABLE accounts ADD COLUMN today_used INT DEFAULT 0 COMMENT '今日已使用次数' AFTER daily_limit;
ALTER TABLE accounts ADD COLUMN last_used_date DATE DEFAULT NULL COMMENT '最后使用日期（用于跨天重置）' AFTER today_used;
```

## 三、核心逻辑

### 3.1 获取账号时（`_try_acquire_account`）

```
① 跨天重置：last_used_date != 今天 → today_used = 0
② SQL过滤：WHERE today_used < daily_limit（排除达上限账号）
③ 锁定时：today_used + 1, last_used_date = CURDATE()
```

### 3.2 跨天自动重置

```sql
UPDATE accounts 
SET today_used = 0, last_used_date = :today
WHERE service_type = :service_type
  AND is_active = 1
  AND (last_used_date IS NULL OR last_used_date != :today)
```

### 3.3 获取可用账号（排除达上限）

```sql
SELECT id, username, password, service_type
FROM accounts 
WHERE service_type = :service_type
  AND is_active = 1
  AND (is_locked = 0 OR (is_locked = 1 AND lock_expiry < :now))
  AND (daily_limit IS NULL OR daily_limit = 0 OR today_used < daily_limit)
ORDER BY use_count ASC, last_used ASC
LIMIT 1
FOR UPDATE SKIP LOCKED
```

### 3.4 锁定时递增计数

```sql
UPDATE accounts 
SET is_locked = 1,
    locked_by = :client_id,
    lock_time = :now,
    lock_expiry = :expiry,
    use_count = use_count + 1,
    today_used = today_used + 1,
    last_used_date = CURDATE(),
    last_used = :now,
    updated_at = :now,
    version = version + 1
WHERE id = :account_id
```

## 四、边界情况处理

| 场景 | 处理方式 |
|------|----------|
| 所有账号达上限 | `acquire_account()` 返回 None，跳过分析 |
| 跨天00:00 | 下次获取时自动重置（`last_used_date != today`） |
| 分析失败 | 仍计入次数（防止无限重试耗尽） |
| 账号被封 | 手动设 `is_active=0` 禁用 |
| `daily_limit=0` 或 NULL | 不限制（兼容旧数据） |
| 动态调整限制 | 直接改表 `daily_limit` 字段，即时生效 |

## 五、日志输出

```
[DeepSeek] 使用账号：xxx@outlook.com
[DeepSeek] 获取账号超时（所有账号今日已达使用上限）
```

## 六、管理命令

```sql
-- 查看今日使用情况
SELECT username, daily_limit, today_used, last_used_date 
FROM accounts 
WHERE service_type = 'deepseek' AND is_active = 1;

-- 调整某账号的每日限制
UPDATE accounts SET daily_limit = 20 WHERE id = 52;

-- 手动重置某账号今日计数
UPDATE accounts SET today_used = 0 WHERE id = 52;

-- 重置所有账号今日计数
UPDATE accounts SET today_used = 0 WHERE service_type = 'deepseek';

-- 禁用账号
UPDATE accounts SET is_active = 0 WHERE id = 52;

-- 查看累计使用统计
SELECT username, use_count, daily_limit, today_used, last_used 
FROM accounts 
WHERE service_type = 'deepseek' 
ORDER BY use_count DESC;
```

## 七、当前配置

| 项目 | 值 |
|------|------|
| 活跃账号数 | 9个 |
| 每账号每日上限 | 10次 |
| 每日总可用次数 | 90次 |
| 跨天重置时间 | 自动（下次获取时） |

## 八、改动文件

| 文件 | 改动 | 提交 |
|------|------|------|
| `src/gs2026/utils/account_pool_util.py` | 跨天重置 + SQL过滤 + 递增today_used | `bc56027` |
| `src/gs2026/analysis/worker/message/deepseek/deepseek_analysis_event_driven.py` | 日志优化（不打印密码） | `bc56027` |
| MySQL `accounts` 表 | 新增3个字段 | 脚本执行 |

## 九、后续优化建议

1. **Dashboard可视化**：在管理面板展示账号使用情况
2. **告警机制**：当可用账号不足时发送告警
3. **动态调整**：根据分析任务量自动调整daily_limit
4. **失败不计数**：分析失败时不递增（需权衡重试风暴风险）
