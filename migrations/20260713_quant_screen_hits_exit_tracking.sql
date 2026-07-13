-- 量化选债命中表扩展：添加退出跟踪字段
-- 使回填和实时选债的结果与回测完全一致

ALTER TABLE quant_screen_hits ADD COLUMN exit_time VARCHAR(20) DEFAULT NULL COMMENT '退出时间(HH:MM:SS)';
ALTER TABLE quant_screen_hits ADD COLUMN exit_price FLOAT DEFAULT NULL COMMENT '退出价格';
ALTER TABLE quant_screen_hits ADD COLUMN profit_pct FLOAT DEFAULT NULL COMMENT '盈亏百分比';
ALTER TABLE quant_screen_hits ADD COLUMN exit_reason VARCHAR(20) DEFAULT NULL COMMENT '退出原因(tp/sl/timeout)';
ALTER TABLE quant_screen_hits ADD COLUMN hold_seconds INT DEFAULT NULL COMMENT '持仓秒数';
ALTER TABLE quant_screen_hits ADD COLUMN max_price FLOAT DEFAULT NULL COMMENT '持仓期间最高价';
ALTER TABLE quant_screen_hits ADD COLUMN min_price FLOAT DEFAULT NULL COMMENT '持仓期间最低价';
