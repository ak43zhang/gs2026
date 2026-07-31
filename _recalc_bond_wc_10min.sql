-- 债券window_count重新计算脚本（SQL窗口函数方案）
-- 使用10分钟区间，按区间内出现顺序计算window_count

SET @date = '20260731';
SET @table_name = CONCAT('monitor_zq_top30_', @date);

-- 步骤1：创建临时表存储区间计算结果
CREATE TEMPORARY TABLE IF NOT EXISTS temp_bond_window_count AS
SELECT 
    code,
    time,
    -- 计算10分钟区间起始 (如 09:40:36 -> 09:40:00)
    CONCAT(
        SUBSTRING(time, 1, 3),
        LPAD(FLOOR(SUBSTRING(time, 4, 2) / 10) * 10, 2, '0'),
        ':00'
    ) as window_start,
    -- 区间内累计次数（从1开始）
    ROW_NUMBER() OVER (
        PARTITION BY code, 
        CONCAT(SUBSTRING(time, 1, 3), LPAD(FLOOR(SUBSTRING(time, 4, 2) / 10) * 10, 2, '0'), ':00')
        ORDER BY time
    ) as calculated_wc
FROM monitor_zq_top30_20260731;

-- 步骤2：更新原表
UPDATE monitor_zq_top30_20260731 t1
JOIN temp_bond_window_count t2 
    ON t1.code = t2.code 
    AND t1.time = t2.time
SET t1.window_count = t2.calculated_wc;

-- 步骤3：验证结果
SELECT 
    SUBSTRING(time, 1, 5) as hour_minute,
    COUNT(*) as tick_count,
    MIN(window_count) as min_wc,
    MAX(window_count) as max_wc,
    AVG(window_count) as avg_wc
FROM monitor_zq_top30_20260731
GROUP BY SUBSTRING(time, 1, 5)
ORDER BY hour_minute;

-- 步骤4：清理临时表
DROP TEMPORARY TABLE IF EXISTS temp_bond_window_count;
