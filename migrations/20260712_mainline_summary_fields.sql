-- 盘中异动 - 市场主线综合分析系统
-- 新增字段到 stock_anomaly_mainline 表
-- 执行日期：2026-07-12

ALTER TABLE stock_anomaly_mainline 
    ADD COLUMN mainline_summary JSON DEFAULT NULL COMMENT '主线综合分析（AI合成）',
    ADD COLUMN synthesis_level VARCHAR(20) DEFAULT NULL COMMENT '合成级别: formation/confirmed',
    ADD COLUMN synthesis_time TIME DEFAULT NULL COMMENT '最近合成时间';
