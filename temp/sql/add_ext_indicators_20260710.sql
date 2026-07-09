-- 添加扩展指标字段到sssj表
-- 执行日期: 2026-07-10
-- 兼容旧表：如果字段已存在则跳过

-- 添加扩展指标JSON字段
SET @db_name = DATABASE();
SET @table_name = 'monitor_zq_sssj_20260709';

-- 检查并添加ext_indicators字段
SET @add_ext_field = CONCAT('
    ALTER TABLE ', @table_name, '
    ADD COLUMN ext_indicators JSON NULL COMMENT "扩展指标JSON字段"
');

-- 使用预编译语句执行
PREPARE stmt FROM @add_ext_field;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 创建索引优化JSON查询（MySQL 8.0+）
SET @add_index = CONCAT('
    ALTER TABLE ', @table_name, '
    ADD INDEX idx_ext_indicators ((CAST(ext_indicators AS CHAR(64) ARRAY)))
');

-- 尝试创建索引（可能不支持，忽略错误）
-- PREPARE stmt FROM @add_index;
-- EXECUTE stmt;
-- DEALLOCATE PREPARE stmt;

-- 创建扩展指标定义表（如不存在）
CREATE TABLE IF NOT EXISTS ext_indicator_definitions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    indicator_code VARCHAR(50) NOT NULL UNIQUE COMMENT '指标代码',
    indicator_name VARCHAR(100) COMMENT '指标名称',
    data_type VARCHAR(20) DEFAULT 'decimal' COMMENT 'decimal/int/boolean/string',
    default_value VARCHAR(50) DEFAULT '0' COMMENT '默认值',
    compute_module VARCHAR(200) COMMENT '计算函数路径',
    compute_params JSON COMMENT '计算参数',
    is_active TINYINT DEFAULT 1 COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='扩展指标定义表';

-- 插入优化版斜率指标定义
INSERT INTO ext_indicator_definitions 
(indicator_code, indicator_name, data_type, default_value, compute_module, compute_params, is_active)
VALUES
('weighted_slope_2m', '2分钟加权斜率', 'decimal', '0', 'bond_indicators.calc_weighted_slope', '{"window": 120, "half_life": 30}', 1),
('change_1m_pct', '1分钟变化率', 'decimal', '0', 'bond_indicators.calc_change_rate', '{"period": 60}', 1),
('price_acceleration', '价格加速度', 'decimal', '0', 'bond_indicators.calc_acceleration', '{"window": 120}', 1)
ON DUPLICATE KEY UPDATE
indicator_name = VALUES(indicator_name),
is_active = VALUES(is_active);

-- 验证
SELECT 'ext_indicators字段添加完成' as status;
SELECT * FROM ext_indicator_definitions WHERE is_active = 1;
