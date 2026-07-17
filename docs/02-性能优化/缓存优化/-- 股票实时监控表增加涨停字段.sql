-- 股票实时监控表增加涨停字段
-- 执行时间: 2026-04-22
-- 影响表: monitor_gp_sssj_{date}

-- ============================================
-- 为现有表增加字段（以2026年表为例）
-- ============================================

-- 为 monitor_gp_sssj_2026 表增加涨停字段
ALTER TABLE monitor_gp_sssj_2026 
ADD COLUMN IF NOT EXISTS is_zt TINYINT(1) DEFAULT 0 COMMENT '是否涨停: 1=是, 0=否',
ADD COLUMN IF NOT EXISTS ever_zt TINYINT(1) DEFAULT 0 COMMENT '曾经涨停: 1=当天有过涨停, 0=没有';

-- 添加索引（用于快速筛选涨停股票）
CREATE INDEX IF NOT EXISTS idx_is_zt ON monitor_gp_sssj_2026(is_zt);
CREATE INDEX IF NOT EXISTS idx_ever_zt ON monitor_gp_sssj_2026(ever_zt);
CREATE INDEX IF NOT EXISTS idx_time_is_zt ON monitor_gp_sssj_2026(time, is_zt);

-- ============================================
-- 查询示例
-- ============================================

-- 查询当前涨停股票
-- SELECT stock_code, short_name, change_pct, time
-- FROM monitor_gp_sssj_20260422
-- WHERE is_zt = 1
-- ORDER BY time DESC;

-- 查询当天曾经涨停的股票
-- SELECT DISTINCT stock_code, short_name
-- FROM monitor_gp_sssj_20260422
-- WHERE ever_zt = 1;

-- 查询某只股票的涨停历史
-- SELECT time, change_pct, is_zt, ever_zt
-- FROM monitor_gp_sssj_20260422
-- WHERE stock_code = '000001'
-- ORDER BY time;

-- ============================================
-- 说明
-- ============================================
-- 1. 新创建的表会自动包含这两个字段（代码已修改）
-- 2. 历史表需要手动执行上述ALTER语句
-- 3. 索引可大幅提升涨停股票查询性能
