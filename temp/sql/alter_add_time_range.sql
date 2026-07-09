-- 为 quant_screen_schemes 表添加时间范围字段
-- 执行日期: 2026-07-10

-- 检查并添加 time_start 字段
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'quant_screen_schemes' 
    AND COLUMN_NAME = 'time_start'
    AND TABLE_SCHEMA = DATABASE()
);

SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE quant_screen_schemes ADD COLUMN time_start VARCHAR(10) DEFAULT "09:30" COMMENT "开始时间"',
    'SELECT "time_start 字段已存在" as message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 time_end 字段
SET @col_exists2 = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'quant_screen_schemes' 
    AND COLUMN_NAME = 'time_end'
    AND TABLE_SCHEMA = DATABASE()
);

SET @sql2 = IF(@col_exists2 = 0, 
    'ALTER TABLE quant_screen_schemes ADD COLUMN time_end VARCHAR(10) DEFAULT "15:00" COMMENT "结束时间"',
    'SELECT "time_end 字段已存在" as message'
);
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- 验证修改
SELECT scheme_name, time_start, time_end, price_offset, offset_mode
FROM quant_screen_schemes 
ORDER BY scheme_name;
