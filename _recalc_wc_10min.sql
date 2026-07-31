-- 重新计算 window_count（10分钟区间）的SQL方案
-- 使用窗口函数，按 code + 10分钟窗口分组

-- 对于 monitor_gp_top30_YYYYMMDD 表
UPDATE monitor_gp_top30_{date_str} t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 3), LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_{date_str}
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;

-- 对于 monitor_zq_top30_YYYYMMDD 表（债券）
UPDATE monitor_zq_top30_{date_str} t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 3), LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_{date_str}
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;
