-- 新闻分析深度分析字段数据库变更（JSON 类型）
-- 执行方式: 在 MySQL 客户端中执行
-- mysql -h 192.168.0.101 -u root -p123456 gs < run_alter_table.sql

-- 删除旧字段（如果存在）
ALTER TABLE analysis_news_detail_2026 DROP COLUMN IF EXISTS deep_analysis;

-- 添加 deep_analysis 字段（JSON 类型）
ALTER TABLE analysis_news_detail_2026 
ADD COLUMN deep_analysis JSON NULL COMMENT '深度分析（JSON数组）'
AFTER sector_details;

-- 验证字段添加成功
SHOW COLUMNS FROM analysis_news_detail_2026 LIKE 'deep_analysis';
