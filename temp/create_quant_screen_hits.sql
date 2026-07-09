-- 量化选债实时信号跟踪命中记录表
-- 创建日期：2026-07-09

CREATE TABLE IF NOT EXISTS quant_screen_hits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date VARCHAR(8) NOT NULL COMMENT '交易日期，如20260709',
    tick_time VARCHAR(6) NOT NULL COMMENT '入场时间点，如143025',
    scheme_name VARCHAR(100) NOT NULL COMMENT '命中方案名称',
    bond_code VARCHAR(10) NOT NULL COMMENT '债券代码',
    bond_name VARCHAR(50) COMMENT '债券名称',
    
    -- 入场信息（固定不变）
    entry_price DECIMAL(10,3) NOT NULL COMMENT '入场价格',
    entry_change_pct DECIMAL(6,2) COMMENT '入场时涨跌幅%',
    entry_amount DECIMAL(15,2) COMMENT '入场时成交金额',
    
    -- 方案参数（固定不变）
    stop_loss_pct DECIMAL(5,2) COMMENT '止损百分比',
    take_profit_pct DECIMAL(5,2) COMMENT '止盈百分比',
    stop_loss_price DECIMAL(10,3) COMMENT '计算后的止损价',
    take_profit_price DECIMAL(10,3) COMMENT '计算后的止盈价',
    max_hold_time INT COMMENT '最大持仓时间（分钟），NULL表示收盘前持续',
    
    -- 当前状态（每tick更新）
    current_price DECIMAL(10,3) COMMENT '当前最新价格',
    current_return_pct DECIMAL(6,2) COMMENT '当前收益率%',
    signal_status VARCHAR(20) COMMENT '信号状态：entry/holding/stopped/profited',
    
    -- 平仓信息（确定后不再更新）
    exit_price DECIMAL(10,3) COMMENT '出场价格',
    exit_time VARCHAR(6) COMMENT '出场时间',
    final_return_pct DECIMAL(6,2) COMMENT '最终收益率%',
    
    -- 状态锁定
    is_locked TINYINT DEFAULT 0 COMMENT '是否锁定：0=跟踪中，1=已锁定',
    locked_at TIMESTAMP NULL COMMENT '锁定时间',
    lock_reason VARCHAR(20) COMMENT '锁定原因：stop_loss/take_profit/max_time/market_close',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    
    -- 索引
    INDEX idx_date_scheme_time (trade_date, scheme_name, tick_time),
    INDEX idx_bond_date (bond_code, trade_date),
    INDEX idx_status (signal_status, is_locked),
    INDEX idx_unlocked (trade_date, is_locked, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='量化选债实时信号跟踪命中记录';
