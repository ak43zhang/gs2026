-- 修复2026-04-24表结构，添加缺失的主力净额字段

-- 检查当前表结构
DESCRIBE monitor_gp_sssj_20260424;

-- 添加主力净额相关字段
ALTER TABLE monitor_gp_sssj_20260424
ADD COLUMN IF NOT EXISTS main_net_amount DECIMAL(15,2) DEFAULT 0 COMMENT '主力净额（元）',
ADD COLUMN IF NOT EXISTS cumulative_main_net DECIMAL(15,2) DEFAULT 0 COMMENT '累计主力净额（元）',
ADD COLUMN IF NOT EXISTS main_behavior VARCHAR(20) DEFAULT NULL COMMENT '主力行为（买入/卖出）',
ADD COLUMN IF NOT EXISTS main_confidence DECIMAL(3,2) DEFAULT 0 COMMENT '主力置信度（0-1）',
ADD COLUMN IF NOT EXISTS delta_amount DECIMAL(15,2) DEFAULT 0 COMMENT '成交额变化',
ADD COLUMN IF NOT EXISTS delta_volume BIGINT DEFAULT 0 COMMENT '成交量变化',
ADD COLUMN IF NOT EXISTS price_diff DECIMAL(10,2) DEFAULT 0 COMMENT '价格变化';

-- 验证字段添加成功
DESCRIBE monitor_gp_sssj_20260424;

-- 检查其他历史表是否也需要修复
-- SELECT TABLE_NAME 
-- FROM information_schema.TABLES 
-- WHERE TABLE_SCHEMA = 'gs' 
-- AND TABLE_NAME LIKE 'monitor_gp_sssj_2026%'
-- AND TABLE_NAME < 'monitor_gp_sssj_20260428';
