-- 添加累计主力净额字段
-- 运行时间：2026-04-28

-- 为今日表添加字段
ALTER TABLE monitor_gp_sssj_20260428
ADD COLUMN IF NOT EXISTS cumulative_main_net DECIMAL(15,2) DEFAULT 0 COMMENT '累计主力净额（元）';

-- 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_cumulative_main_net 
ON monitor_gp_sssj_20260428(stock_code, time, cumulative_main_net);

-- 为历史数据填充累计值（可选，仅填充今日数据）
-- 注意：这个UPDATE可能需要较长时间，请在低峰期运行
/*
UPDATE monitor_gp_sssj_20260428 t1
JOIN (
    SELECT 
        stock_code,
        time,
        SUM(main_net_amount) OVER (
            PARTITION BY stock_code 
            ORDER BY time 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as calculated_cumulative
    FROM monitor_gp_sssj_20260428
) t2 ON t1.stock_code = t2.stock_code AND t1.time = t2.time
SET t1.cumulative_main_net = t2.calculated_cumulative
WHERE t1.cumulative_main_net = 0 OR t1.cumulative_main_net IS NULL;
*/
