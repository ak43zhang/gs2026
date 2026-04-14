-- ============================================
-- 股票-债券-行业 1对1对1 映射关系 SQL
-- ============================================

-- 主查询: 获取股票、债券、行业的 1对1对1 关系
SELECT 
    ic.stock_code AS stock_code,        -- 股票代码
    ic.short_name AS short_name,        -- 股票简称
    b.bond_code AS bond_code,           -- 债券代码
    b.bond_name AS bond_name,           -- 债券简称
    ic.name AS industry_name            -- 行业名称
FROM data_industry_code_component_ths ic
INNER JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
WHERE ic.stock_code IS NOT NULL 
  AND ic.stock_code != ''
  AND b.bond_code IS NOT NULL
  AND b.bond_code != ''
ORDER BY ic.stock_code;

-- ============================================
-- 变体查询
-- ============================================

-- 变体1: 使用 DISTINCT 去重
SELECT DISTINCT
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name AS industry_name
FROM data_industry_code_component_ths ic
INNER JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
WHERE ic.stock_code IS NOT NULL 
  AND ic.stock_code != ''
ORDER BY ic.stock_code;

-- 变体2: LEFT JOIN (保留所有股票，包括无债券的)
SELECT 
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name AS industry_name
FROM data_industry_code_component_ths ic
LEFT JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
WHERE ic.stock_code IS NOT NULL 
  AND ic.stock_code != ''
ORDER BY ic.stock_code;

-- 变体3: 按行业分组统计
SELECT 
    ic.name AS industry_name,
    COUNT(DISTINCT ic.stock_code) AS stock_count,
    COUNT(DISTINCT b.bond_code) AS bond_count
FROM data_industry_code_component_ths ic
LEFT JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
WHERE ic.stock_code IS NOT NULL 
  AND ic.stock_code != ''
GROUP BY ic.name
ORDER BY stock_count DESC;

-- ============================================
-- 创建映射关系表
-- ============================================

-- 创建结果表
CREATE TABLE IF NOT EXISTS stock_bond_industry_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    short_name VARCHAR(100) COMMENT '股票简称',
    bond_code VARCHAR(20) COMMENT '债券代码',
    bond_name VARCHAR(100) COMMENT '债券简称',
    industry_name VARCHAR(100) COMMENT '行业名称',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    UNIQUE KEY uk_stock_code (stock_code),
    INDEX idx_bond_code (bond_code),
    INDEX idx_industry (industry_name),
    INDEX idx_short_name (short_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票-债券-行业映射关系表';

-- 清空并插入数据
TRUNCATE TABLE stock_bond_industry_mapping;

INSERT INTO stock_bond_industry_mapping 
    (stock_code, short_name, bond_code, bond_name, industry_name)
SELECT DISTINCT
    ic.stock_code,
    ic.short_name,
    b.bond_code,
    b.bond_name,
    ic.name
FROM data_industry_code_component_ths ic
INNER JOIN data_bond_ths b 
    ON ic.stock_code = b.stock_code
WHERE ic.stock_code IS NOT NULL 
  AND ic.stock_code != ''
  AND b.bond_code IS NOT NULL
  AND b.bond_code != ''
ORDER BY ic.stock_code;

-- 查询结果
SELECT * FROM stock_bond_industry_mapping LIMIT 10;

-- 统计信息
SELECT 
    COUNT(*) AS total_records,
    COUNT(DISTINCT stock_code) AS unique_stocks,
    COUNT(DISTINCT bond_code) AS unique_bonds,
    COUNT(DISTINCT industry_name) AS unique_industries
FROM stock_bond_industry_mapping;
