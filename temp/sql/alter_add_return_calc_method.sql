-- 添加总收益计算方式字段到方案表
-- 执行日期: 2026-07-10

ALTER TABLE quant_screen_schemes 
ADD COLUMN IF NOT EXISTS return_calc_method VARCHAR(20) DEFAULT 'compound' COMMENT '总收益计算方式: compound(复利), average(平均), curve(资金曲线)';

-- 更新现有方案为默认值
UPDATE quant_screen_schemes SET return_calc_method = 'compound' WHERE return_calc_method IS NULL;

-- 验证
SELECT name, return_calc_method FROM quant_screen_schemes;
