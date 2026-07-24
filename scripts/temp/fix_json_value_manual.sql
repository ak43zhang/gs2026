-- ============================================
-- 修复 json_value 字段空间不足问题
-- 执行方式：在 MySQL 客户端或管理工具中执行
-- ============================================

-- 问题：text 类型最大 64KB，DeepSeek/火山分析结果可能超过此限制
-- 解决：改为 longtext 类型，最大 4GB

-- 1. 修复 analysis_news2026 表
ALTER TABLE analysis_news2026 MODIFY COLUMN json_value LONGTEXT;

-- 2. 修复 analysis_notices2026 表  
ALTER TABLE analysis_notices2026 MODIFY COLUMN json_value LONGTEXT;

-- 3. 修复 analysis_notices2025 表
ALTER TABLE analysis_notices2025 MODIFY COLUMN json_value LONGTEXT;

-- 可选：检查修改结果
-- SHOW COLUMNS FROM analysis_news2026;
-- SHOW COLUMNS FROM analysis_notices2026;
-- SHOW COLUMNS FROM analysis_notices2025;
