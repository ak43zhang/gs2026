-- 新闻分析深度分析字段数据库变更
-- 执行时间: 2026-04-17
-- 功能: 为 analysis_news_detail_2026 表添加 deep_analysis 字段

-- 添加 deep_analysis 字段
ALTER TABLE analysis_news_detail_2026 
ADD COLUMN deep_analysis TEXT NULL COMMENT '深度分析（JSON数组）'
AFTER sector_details;

-- 验证字段添加成功
-- SHOW COLUMNS FROM analysis_news_detail_2026 LIKE 'deep_analysis';

-- 回滚SQL（如需回滚）
-- ALTER TABLE analysis_news_detail_2026 DROP COLUMN deep_analysis;
