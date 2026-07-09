-- 为 quant_screen_schemes 表添加价格偏移字段
-- 执行日期: 2026-07-09

-- 检查并添加 price_offset 字段
SET @col_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'quant_screen_schemes' 
    AND COLUMN_NAME = 'price_offset'
    AND TABLE_SCHEMA = DATABASE()
);

SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE quant_screen_schemes ADD COLUMN price_offset DECIMAL(10,4) DEFAULT 0.0 COMMENT "价格偏移（元或百分比）"',
    'SELECT "price_offset 字段已存在" as message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 offset_mode 字段
SET @col_exists2 = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'quant_screen_schemes' 
    AND COLUMN_NAME = 'offset_mode'
    AND TABLE_SCHEMA = DATABASE()
);

SET @sql2 = IF(@col_exists2 = 0, 
    'ALTER TABLE quant_screen_schemes ADD COLUMN offset_mode VARCHAR(20) DEFAULT "fixed" COMMENT "偏移模式：fixed/percent"',
    'SELECT "offset_mode 字段已存在" as message'
);
PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- 更新现有方案：大盘债券斜率共振设置默认偏移0.1元
UPDATE quant_screen_schemes 
SET price_offset = 0.1, offset_mode = 'fixed'
WHERE scheme_name = '大盘债券斜率共振' AND price_offset = 0.0;

-- 验证修改
SELECT scheme_name, price_offset, offset_mode 
FROM quant_screen_schemes 
ORDER BY scheme_name;
