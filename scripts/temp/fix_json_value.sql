-- 修复 json_value 字段空间不足问题
-- 将 text (64KB) 改为 longtext (4GB)

-- analysis_news2026
ALTER TABLE analysis_news2026 MODIFY COLUMN json_value LONGTEXT;

-- analysis_notices2026
ALTER TABLE analysis_notices2026 MODIFY COLUMN json_value LONGTEXT;

-- analysis_notices2025
ALTER TABLE analysis_notices2025 MODIFY COLUMN json_value LONGTEXT;

-- 检查是否还有其他表需要修改
-- 可以添加更多表...
