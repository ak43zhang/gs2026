-- 为 sssj 表添加优化版斜率指标字段
-- 执行日期: 2026-07-10
-- 适用表: monitor_zq_sssj_YYYYMMDD

-- 添加新指标字段
ALTER TABLE {table_name} 
ADD COLUMN IF NOT EXISTS weighted_slope_2m DECIMAL(10,6) DEFAULT 0 COMMENT '2分钟加权斜率',
ADD COLUMN IF NOT EXISTS change_1m_pct DECIMAL(6,4) DEFAULT 0 COMMENT '1分钟变化率%',
ADD COLUMN IF NOT EXISTS price_acceleration DECIMAL(10,6) DEFAULT 0 COMMENT '价格加速度',
ADD COLUMN IF NOT EXISTS mkt_weighted_slope_2m DECIMAL(10,6) DEFAULT 0 COMMENT '大盘2分钟加权斜率',
ADD COLUMN IF NOT EXISTS mkt_change_1m_pct DECIMAL(6,4) DEFAULT 0 COMMENT '大盘1分钟变化率%',
ADD COLUMN IF NOT EXISTS mkt_acceleration DECIMAL(10,6) DEFAULT 0 COMMENT '大盘价格加速度';

-- 创建索引优化查询
CREATE INDEX IF NOT EXISTS idx_weighted_slope ON {table_name}(weighted_slope_2m);
CREATE INDEX IF NOT EXISTS idx_change_1m ON {table_name}(change_1m_pct);
