-- 修改 scheduler_jobs 表，支持三种任务类型
-- 执行时间: 2026-04-01

-- 1. 修改 job_type 字段，添加新的枚举值
ALTER TABLE scheduler_jobs 
MODIFY COLUMN job_type ENUM('function', 'script', 'scheduler') NOT NULL COMMENT '任务类型: function-函数调用, script-脚本执行, scheduler-任务调度';

-- 2. 添加 params 字段到执行记录表（如果不存在）
ALTER TABLE scheduler_executions 
ADD COLUMN IF NOT EXISTS params JSON NULL COMMENT '执行参数' AFTER trigger_type;

-- 3. 创建索引优化查询
CREATE INDEX IF NOT EXISTS idx_executions_job_id ON scheduler_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON scheduler_executions(status);
