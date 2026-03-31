-- Dashboard2 Scheduler Database Tables
-- Created: 2026-03-30

-- Table 1: scheduler_jobs
CREATE TABLE IF NOT EXISTS scheduler_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'Job unique ID',
    job_name VARCHAR(128) NOT NULL COMMENT 'Job name',
    job_type ENUM('redis_cache', 'dashboard_task', 'python_script', 'chain') 
        NOT NULL COMMENT 'Job type',
    job_config JSON NOT NULL COMMENT 'Job config JSON',
    trigger_type ENUM('cron', 'interval', 'date', 'once') 
        NOT NULL DEFAULT 'cron' COMMENT 'Trigger type',
    trigger_config JSON NOT NULL COMMENT 'Trigger config JSON',
    parent_job_id VARCHAR(64) DEFAULT NULL COMMENT 'Parent job ID',
    next_job_ids JSON DEFAULT NULL COMMENT 'Next job IDs array',
    chain_condition ENUM('always', 'on_success', 'on_failure') 
        DEFAULT 'on_success' COMMENT 'Chain condition',
    status ENUM('enabled', 'disabled', 'running', 'error') 
        DEFAULT 'enabled' COMMENT 'Job status',
    last_run_time DATETIME COMMENT 'Last run time',
    last_run_status ENUM('success', 'failed', 'timeout') COMMENT 'Last run status',
    last_run_message TEXT COMMENT 'Last run message',
    run_count INT DEFAULT 0 COMMENT 'Run count',
    fail_count INT DEFAULT 0 COMMENT 'Fail count',
    description TEXT COMMENT 'Description',
    created_by VARCHAR(64) COMMENT 'Created by',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_job_type (job_type),
    INDEX idx_status (status),
    INDEX idx_parent_job (parent_job_id),
    INDEX idx_last_run_time (last_run_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Scheduler jobs table';

-- Table 2: scheduler_execution_log
CREATE TABLE IF NOT EXISTS scheduler_execution_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL COMMENT 'Job ID',
    execution_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'Execution unique ID',
    trigger_type ENUM('scheduled', 'manual', 'chain') DEFAULT 'scheduled' 
        COMMENT 'Trigger type',
    parent_execution_id VARCHAR(64) DEFAULT NULL COMMENT 'Parent execution ID',
    start_time DATETIME NOT NULL COMMENT 'Start time',
    end_time DATETIME COMMENT 'End time',
    duration_seconds INT COMMENT 'Duration in seconds',
    status ENUM('pending', 'running', 'success', 'failed', 'timeout', 'skipped') 
        DEFAULT 'pending' COMMENT 'Execution status',
    result_message TEXT COMMENT 'Result message',
    error_type VARCHAR(64) COMMENT 'Error type',
    error_stack TEXT COMMENT 'Error stack',
    output_log TEXT COMMENT 'Output log',
    next_executions JSON COMMENT 'Next execution IDs',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_job_id (job_id),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time),
    INDEX idx_parent_execution (parent_execution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Scheduler execution log table';

-- Sample data 1: Redis cache job
INSERT INTO scheduler_jobs (
    job_id, job_name, job_type, job_config, trigger_type, trigger_config,
    description, created_by
) VALUES (
    'red_list_cache_daily',
    'Daily Red List Cache Update',
    'redis_cache',
    '{"cache_type": "red_list", "function": "update_red_list_cache", "module": "gs2026.dashboard2.routes.red_list_cache", "params": {"date": null}}',
    'cron',
    '{"minute": "30", "hour": "9", "day": "*", "month": "*", "day_of_week": "mon-fri"}',
    'Update red list cache at 9:30 on weekdays',
    'system'
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- Sample data 2: Dashboard collection job
INSERT INTO scheduler_jobs (
    job_id, job_name, job_type, job_config, trigger_type, trigger_config,
    description, created_by
) VALUES (
    'collect_ztb_daily',
    'Daily ZTB Data Collection',
    'dashboard_task',
    '{"task_category": "collection", "task_id": "ztb", "params": {"date": null}}',
    'cron',
    '{"minute": "35", "hour": "9", "day": "*", "month": "*", "day_of_week": "mon-fri"}',
    'Collect ZTB data at 9:35 on weekdays',
    'system'
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- Sample data 3: Python script job
INSERT INTO scheduler_jobs (
    job_id, job_name, job_type, job_config, trigger_type, trigger_config,
    description, created_by
) VALUES (
    'combine_collection_daily',
    'Daily Data Combine',
    'python_script',
    '{"script_path": "gs2026.analysis.worker.message.deepseek.combine_collection", "function": "main", "params": {"base_date": null}, "working_dir": "F:/pyworkspace2026/gs2026", "timeout": 3600}',
    'cron',
    '{"minute": "0", "hour": "15", "day": "*", "month": "*", "day_of_week": "mon-fri"}',
    'Run data combine script at 15:00 on weekdays',
    'system'
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
