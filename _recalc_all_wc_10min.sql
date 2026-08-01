-- 批量重新计算 window_count（10分钟区间）
-- 适用于 monitor_gp_top30 和 monitor_zq_top30 表
-- 执行前请备份数据！

-- ========== 日期: 20260622 ==========

-- 股票表 monitor_gp_top30_20260622
UPDATE monitor_gp_top30_20260622 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260622
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260622
UPDATE monitor_zq_top30_20260622 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260622
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260623 ==========

-- 股票表 monitor_gp_top30_20260623
UPDATE monitor_gp_top30_20260623 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260623
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260623
UPDATE monitor_zq_top30_20260623 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260623
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260624 ==========

-- 股票表 monitor_gp_top30_20260624
UPDATE monitor_gp_top30_20260624 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260624
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260624
UPDATE monitor_zq_top30_20260624 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260624
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260625 ==========

-- 股票表 monitor_gp_top30_20260625
UPDATE monitor_gp_top30_20260625 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260625
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260625
UPDATE monitor_zq_top30_20260625 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260625
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260626 ==========

-- 股票表 monitor_gp_top30_20260626
UPDATE monitor_gp_top30_20260626 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260626
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260626
UPDATE monitor_zq_top30_20260626 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260626
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260629 ==========

-- 股票表 monitor_gp_top30_20260629
UPDATE monitor_gp_top30_20260629 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260629
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260629
UPDATE monitor_zq_top30_20260629 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260629
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260630 ==========

-- 股票表 monitor_gp_top30_20260630
UPDATE monitor_gp_top30_20260630 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260630
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260630
UPDATE monitor_zq_top30_20260630 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260630
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260701 ==========

-- 股票表 monitor_gp_top30_20260701
UPDATE monitor_gp_top30_20260701 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260701
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260701
UPDATE monitor_zq_top30_20260701 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260701
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260702 ==========

-- 股票表 monitor_gp_top30_20260702
UPDATE monitor_gp_top30_20260702 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260702
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260702
UPDATE monitor_zq_top30_20260702 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260702
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260703 ==========

-- 股票表 monitor_gp_top30_20260703
UPDATE monitor_gp_top30_20260703 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260703
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260703
UPDATE monitor_zq_top30_20260703 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260703
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260706 ==========

-- 股票表 monitor_gp_top30_20260706
UPDATE monitor_gp_top30_20260706 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260706
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260706
UPDATE monitor_zq_top30_20260706 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260706
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260707 ==========

-- 股票表 monitor_gp_top30_20260707
UPDATE monitor_gp_top30_20260707 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260707
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260707
UPDATE monitor_zq_top30_20260707 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260707
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260708 ==========

-- 股票表 monitor_gp_top30_20260708
UPDATE monitor_gp_top30_20260708 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260708
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260708
UPDATE monitor_zq_top30_20260708 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260708
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260709 ==========

-- 股票表 monitor_gp_top30_20260709
UPDATE monitor_gp_top30_20260709 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260709
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260709
UPDATE monitor_zq_top30_20260709 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260709
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260710 ==========

-- 股票表 monitor_gp_top30_20260710
UPDATE monitor_gp_top30_20260710 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260710
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260710
UPDATE monitor_zq_top30_20260710 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260710
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260713 ==========

-- 股票表 monitor_gp_top30_20260713
UPDATE monitor_gp_top30_20260713 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260713
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260713
UPDATE monitor_zq_top30_20260713 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260713
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260714 ==========

-- 股票表 monitor_gp_top30_20260714
UPDATE monitor_gp_top30_20260714 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260714
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260714
UPDATE monitor_zq_top30_20260714 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260714
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260715 ==========

-- 股票表 monitor_gp_top30_20260715
UPDATE monitor_gp_top30_20260715 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260715
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260715
UPDATE monitor_zq_top30_20260715 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260715
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260716 ==========

-- 股票表 monitor_gp_top30_20260716
UPDATE monitor_gp_top30_20260716 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260716
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260716
UPDATE monitor_zq_top30_20260716 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260716
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260717 ==========

-- 股票表 monitor_gp_top30_20260717
UPDATE monitor_gp_top30_20260717 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260717
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260717
UPDATE monitor_zq_top30_20260717 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260717
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260720 ==========

-- 股票表 monitor_gp_top30_20260720
UPDATE monitor_gp_top30_20260720 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260720
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260720
UPDATE monitor_zq_top30_20260720 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260720
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260721 ==========

-- 股票表 monitor_gp_top30_20260721
UPDATE monitor_gp_top30_20260721 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260721
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260721
UPDATE monitor_zq_top30_20260721 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260721
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260722 ==========

-- 股票表 monitor_gp_top30_20260722
UPDATE monitor_gp_top30_20260722 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260722
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260722
UPDATE monitor_zq_top30_20260722 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260722
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260723 ==========

-- 股票表 monitor_gp_top30_20260723
UPDATE monitor_gp_top30_20260723 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260723
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260723
UPDATE monitor_zq_top30_20260723 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260723
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260724 ==========

-- 股票表 monitor_gp_top30_20260724
UPDATE monitor_gp_top30_20260724 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260724
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260724
UPDATE monitor_zq_top30_20260724 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260724
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260727 ==========

-- 股票表 monitor_gp_top30_20260727
UPDATE monitor_gp_top30_20260727 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260727
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260727
UPDATE monitor_zq_top30_20260727 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260727
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260728 ==========

-- 股票表 monitor_gp_top30_20260728
UPDATE monitor_gp_top30_20260728 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260728
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260728
UPDATE monitor_zq_top30_20260728 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260728
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260729 ==========

-- 股票表 monitor_gp_top30_20260729
UPDATE monitor_gp_top30_20260729 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260729
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260729
UPDATE monitor_zq_top30_20260729 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260729
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260730 ==========

-- 股票表 monitor_gp_top30_20260730
UPDATE monitor_gp_top30_20260730 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260730
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260730
UPDATE monitor_zq_top30_20260730 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260730
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- ========== 日期: 20260731 ==========

-- 股票表 monitor_gp_top30_20260731
UPDATE monitor_gp_top30_20260731 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_gp_top30_20260731
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;


-- 债券表 monitor_zq_top30_20260731
UPDATE monitor_zq_top30_20260731 t1
JOIN (
    SELECT 
        code,
        time,
        ROW_NUMBER() OVER (
            PARTITION BY code, 
            CONCAT(SUBSTRING(time, 1, 2), ':', LPAD(FLOOR(SUBSTRING(time, 4, 2)/10)*10, 2, '0'), ':00')
            ORDER BY time
        ) as new_window_count
    FROM monitor_zq_top30_20260731
) t2 ON t1.code = t2.code AND t1.time = t2.time
SET t1.window_count = t2.new_window_count;

