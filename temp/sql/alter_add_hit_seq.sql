-- 添加命中次序列到 quant_screen_hits 表

ALTER TABLE quant_screen_hits 
ADD COLUMN IF NOT EXISTS hit_seq_today INT DEFAULT 1 COMMENT '当天命中序号';

-- 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_bond_date_time ON quant_screen_hits(bond_code, trade_date, tick_time);
