-- 填充688126的max_cumulative_main_net数据
-- 步骤1: 检查字段是否存在，不存在则添加
-- 步骤2: 计算并更新max_cumulative_main_net

-- 先查看688126的数据情况
SELECT 
    time_str,
    stock_code,
    cumulative_main_net,
    COALESCE(max_cumulative_main_net, 0) as current_max
FROM monitor_gp_sssj_20260512 
WHERE stock_code = '688126' 
ORDER BY time_str ASC 
LIMIT 10;

-- 计算峰值（累计值的最大值）
SELECT 
    MAX(cumulative_main_net) as peak_value,
    COUNT(*) as total_records
FROM monitor_gp_sssj_20260512 
WHERE stock_code = '688126';

-- 更新所有记录的max_cumulative_main_net为峰值
-- UPDATE monitor_gp_sssj_20260512 
-- SET max_cumulative_main_net = (SELECT MAX(cumulative_main_net) FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126')
-- WHERE stock_code = '688126';
