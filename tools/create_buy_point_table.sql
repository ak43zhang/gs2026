-- 买点候选记录表
CREATE TABLE IF NOT EXISTS buy_point_candidates (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    date                DATE NOT NULL,
    time                TIME NOT NULL,
    
    -- 股票信息
    stock_code          VARCHAR(10) NOT NULL,
    stock_name          VARCHAR(50),
    stock_price         DECIMAL(10,2),
    stock_change_pct    DECIMAL(5,2),
    
    -- 债券信息
    bond_code           VARCHAR(10),
    bond_price          DECIMAL(10,2),
    bond_change_pct     DECIMAL(5,2),
    
    -- 评级
    level               TINYINT COMMENT '1-3星',
    condition_count     TINYINT COMMENT '满足条件数',
    total_conditions    TINYINT COMMENT '总条件数',
    
    -- 条件详情 (JSON)
    conditions          JSON COMMENT '各条件详情',
    
    -- 大盘环境 (JSON)
    market_context      JSON COMMENT '大盘评分和状态',
    
    -- 结果跟踪
    result_5m_price     DECIMAL(10,2),
    result_5m_change    DECIMAL(5,2),
    result_15m_price    DECIMAL(10,2),
    result_15m_change   DECIMAL(5,2),
    result_30m_price    DECIMAL(10,2),
    result_30m_change   DECIMAL(5,2),
    result_close_price  DECIMAL(10,2),
    result_close_change DECIMAL(5,2),
    
    -- 统计标记
    is_success_5m       BOOLEAN,
    is_success_15m      BOOLEAN,
    is_success_30m      BOOLEAN,
    is_success_close    BOOLEAN,
    
    -- 元数据
    is_valid            BOOLEAN DEFAULT TRUE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_date_time (date, time),
    INDEX idx_stock_code (stock_code),
    INDEX idx_bond_code (bond_code),
    INDEX idx_level (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='买点候选记录表';
