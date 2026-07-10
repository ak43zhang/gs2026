-- 创建回测历史记录表（持久化，排行榜模式）

CREATE TABLE IF NOT EXISTS backtest_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hash VARCHAR(64) NOT NULL UNIQUE,
    total_return_pct DECIMAL(10,4) NOT NULL,
    signal_count INT DEFAULT 0,
    win_rate DECIMAL(6,2) DEFAULT 0,
    date_range VARCHAR(50),
    scheme_name VARCHAR(100),
    params JSON,
    summary_preview JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_return (total_return_pct DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测历史记录（排行榜模式，保留收益最高30条）';
