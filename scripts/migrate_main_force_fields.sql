-- 主力净额字段数据库迁移脚本
-- 创建时间：2026-04-28
-- 用途：为 monitor_gp_sssj_{date} 表添加主力净额相关字段

-- 添加主力净额字段
ALTER TABLE monitor_gp_sssj_20260428 ADD COLUMN IF NOT EXISTS (
    main_net_amount DECIMAL(15,2) DEFAULT 0 COMMENT '主力净额（元），正值=净流入，负值=净流出',
    main_behavior VARCHAR(20) DEFAULT '' COMMENT '主力行为类型',
    main_confidence DECIMAL(3,2) DEFAULT 0 COMMENT '置信度（0-1）'
);

-- 为新字段添加索引（可选，根据查询需求）
-- CREATE INDEX idx_main_net_amount ON monitor_gp_sssj_20260428 (main_net_amount);
-- CREATE INDEX idx_main_behavior ON monitor_gp_sssj_20260428 (main_behavior);
