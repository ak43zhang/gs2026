-- 回测历史增加完整结果存储字段
-- 执行日期：2026-07-12

ALTER TABLE backtest_history 
    ADD COLUMN result_data JSON DEFAULT NULL COMMENT '完整回测结果数据（交易明细等）';
