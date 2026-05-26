-- 报表中心数据库脚本
-- 数据库: gs_platform
-- 创建时间: 2026-04-03

USE gs_platform;

-- 1. 报告类型配置表
CREATE TABLE IF NOT EXISTS report_types (
    report_type_id          INT PRIMARY KEY AUTO_INCREMENT COMMENT '类型ID',
    report_type_code        VARCHAR(50) UNIQUE NOT NULL COMMENT '类型代码',
    report_type_name        VARCHAR(100) NOT NULL COMMENT '类型名称',
    report_type_icon        VARCHAR(50) DEFAULT '📄' COMMENT '图标',
    report_type_description TEXT COMMENT '类型描述',
    report_type_output_dir  VARCHAR(200) NOT NULL COMMENT '输出目录',
    report_type_default_format VARCHAR(20) DEFAULT 'pdf' COMMENT '默认格式',
    report_type_supported_formats JSON COMMENT '支持的格式列表',
    report_type_is_active   BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    report_type_sort_order  INT DEFAULT 0 COMMENT '排序顺序',
    report_type_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_type_updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_report_type_active (report_type_is_active, report_type_sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告类型配置表';

-- 2. 报告元数据表
CREATE TABLE IF NOT EXISTS reports (
    report_id               INT PRIMARY KEY AUTO_INCREMENT COMMENT '报告ID',
    report_type             VARCHAR(50) NOT NULL COMMENT '报告类型代码',
    report_name             VARCHAR(255) NOT NULL COMMENT '报告名称',
    report_date             DATE NOT NULL COMMENT '报告日期',
    report_file_path        VARCHAR(500) NOT NULL COMMENT '文件相对路径',
    report_file_format      VARCHAR(20) NOT NULL COMMENT '文件格式',
    report_file_size        BIGINT DEFAULT 0 COMMENT '文件大小(字节)',
    report_page_count       INT DEFAULT 0 COMMENT '页数/章节数',
    report_content_text     LONGTEXT COMMENT '纯文本内容（TTS用）',
    report_tts_status       VARCHAR(20) DEFAULT 'pending' COMMENT '语音状态',
    report_tts_duration     INT DEFAULT 0 COMMENT '语音时长(秒)',
    report_tts_audio_path   VARCHAR(500) COMMENT '语音文件相对路径',
    report_params           JSON COMMENT '生成参数',
    report_status           VARCHAR(20) DEFAULT 'completed' COMMENT '报告状态',
    report_created_at       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_report_type_date (report_type, report_date),
    INDEX idx_report_format (report_file_format),
    INDEX idx_report_date (report_date),
    INDEX idx_report_tts_status (report_tts_status),
    INDEX idx_report_status (report_status),
    FULLTEXT INDEX idx_report_content (report_content_text),
    
    CONSTRAINT fk_report_type 
        FOREIGN KEY (report_type) REFERENCES report_types(report_type_code)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告元数据表';

-- 3. 报告生成任务表
CREATE TABLE IF NOT EXISTS report_tasks (
    report_task_id          VARCHAR(50) PRIMARY KEY COMMENT '任务ID',
    report_type             VARCHAR(50) NOT NULL COMMENT '报告类型',
    report_date             DATE NOT NULL COMMENT '报告日期',
    report_format           VARCHAR(20) COMMENT '目标格式',
    report_task_status      VARCHAR(20) DEFAULT 'pending' COMMENT '任务状态',
    report_task_progress    INT DEFAULT 0 COMMENT '进度百分比',
    report_task_message     TEXT COMMENT '状态消息',
    report_task_params      JSON COMMENT '生成参数',
    report_task_result_id   INT COMMENT '生成的报告ID',
    report_task_error       TEXT COMMENT '错误信息',
    report_task_started_at  DATETIME COMMENT '开始时间',
    report_task_completed_at DATETIME COMMENT '完成时间',
    report_task_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_task_updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_report_task_status (report_task_status),
    INDEX idx_report_task_type_date (report_type, report_date),
    INDEX idx_report_task_created (report_task_created_at),
    
    CONSTRAINT fk_report_task_type 
        FOREIGN KEY (report_type) REFERENCES report_types(report_type_code)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_report_task_result 
        FOREIGN KEY (report_task_result_id) REFERENCES reports(report_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告生成任务表';

-- 初始化报告类型数据
INSERT INTO report_types (
    report_type_code, report_type_name, report_type_icon, 
    report_type_output_dir, report_type_default_format, 
    report_type_supported_formats, report_type_sort_order
) VALUES
('zt_report', '涨停报告', '📈', 'zt_report', 'pdf', 
 '["pdf", "epub", "md", "html"]', 1),
('event_report', '领域事件报告', '📰', 'event_report', 'pdf', 
 '["pdf", "epub", "md", "docx"]', 2),
('data_report', '数据报表', '📊', 'data_report', 'xlsx', 
 '["xlsx", "pdf", "epub", "html"]', 3)
ON DUPLICATE KEY UPDATE 
    report_type_name = VALUES(report_type_name),
    report_type_supported_formats = VALUES(report_type_supported_formats);

-- 验证创建结果
SELECT 'Tables created successfully' AS result;
SHOW TABLES;
