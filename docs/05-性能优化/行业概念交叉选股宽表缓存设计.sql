-- 行业概念交叉选股宽表缓存设计
-- 创建时间: 2026-04-21
-- 用途: 缓存股票的行业、概念、债券映射关系，加速交叉选股查询

CREATE TABLE IF NOT EXISTS `cache_stock_industry_concept_bond` (
    `stock_code` VARCHAR(10) NOT NULL COMMENT '股票代码',
    `stock_name` VARCHAR(20) DEFAULT NULL COMMENT '股票名称',
    `industry_codes` JSON DEFAULT NULL COMMENT '所属行业代码列表 ["881121", ...]',
    `industry_names` JSON DEFAULT NULL COMMENT '所属行业名称列表 ["半导体", ...]',
    `concept_codes` JSON DEFAULT NULL COMMENT '所属概念代码列表 ["309055", ...]',
    `concept_names` JSON DEFAULT NULL COMMENT '所属概念名称列表 ["6G概念", ...]',
    `bond_code` VARCHAR(10) DEFAULT NULL COMMENT '可转债代码',
    `bond_name` VARCHAR(50) DEFAULT NULL COMMENT '可转债名称',
    `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`stock_code`),
    KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票行业概念债券宽表缓存';
