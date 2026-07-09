#!/usr/bin/env python3
"""创建 quant_screen_schemes 表"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from gs2026.utils.config import Config
from sqlalchemy import create_engine, text

config = Config()
engine = create_engine(
    f'mysql+pymysql://{config.mysql_user}:{config.mysql_password}@{config.mysql_host}:{config.mysql_port}/{config.mysql_db}?charset=utf8mb4'
)

sql = """
CREATE TABLE IF NOT EXISTS quant_screen_schemes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scheme_name VARCHAR(100) NOT NULL COMMENT '方案名称',
    scheme_desc VARCHAR(500) COMMENT '方案描述',
    conditions_json TEXT NOT NULL COMMENT '筛选条件JSON',
    stop_loss_pct DECIMAL(5,2) DEFAULT 3.0 COMMENT '止损百分比',
    take_profit_pct DECIMAL(5,2) DEFAULT 5.0 COMMENT '止盈百分比',
    max_hold_time INT DEFAULT 30 COMMENT '最大持仓时间(分钟)',
    is_active TINYINT DEFAULT 1 COMMENT '是否在用',
    use_backtest TINYINT DEFAULT 1 COMMENT '回测使用',
    use_realtime TINYINT DEFAULT 1 COMMENT '实时选股使用',
    use_replay TINYINT DEFAULT 1 COMMENT '回放使用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (scheme_name),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='量化选债方案表';
"""

with engine.connect() as conn:
    conn.execute(text(sql))
    
    # 插入默认方案
    insert_sql = """
    INSERT INTO quant_screen_schemes 
    (scheme_name, scheme_desc, conditions_json, stop_loss_pct, take_profit_pct, max_hold_time, is_active, use_backtest, use_realtime, use_replay)
    VALUES 
    ('强势反弹', '涨跌幅大于2%且成交额大于100万', '[{\"field\":\"change_pct\",\"op\":\">\",\"value\":2,\"logic\":\"AND\"},{\"field\":\"amount\",\"op\":\">\",\"value\":1000000,\"logic\":\"AND\"}]', 3.0, 5.0, 30, 1, 1, 1, 1),
    ('高成交额', '成交额大于500万', '[{\"field\":\"amount\",\"op\":\">\",\"value\":5000000,\"logic\":\"AND\"}]', 2.0, 3.0, NULL, 1, 1, 1, 1),
    ('大盘债券斜率共振', '大盘斜率>0.5且债券斜率>0.3且成交额>100万', '[{\"field\":\"mkt_slope_short\",\"op\":\">\",\"value\":0.5,\"logic\":\"AND\"},{\"field\":\"slope_short\",\"op\":\">\",\"value\":0.3,\"logic\":\"AND\"},{\"field\":\"amount\",\"op\":\">\",\"value\":1000000,\"logic\":\"AND\"}]', 2.0, 4.0, 30, 1, 1, 1, 1)
    ON DUPLICATE KEY UPDATE
        scheme_desc = VALUES(scheme_desc),
        conditions_json = VALUES(conditions_json),
        stop_loss_pct = VALUES(stop_loss_pct),
        take_profit_pct = VALUES(take_profit_pct),
        max_hold_time = VALUES(max_hold_time),
        is_active = VALUES(is_active),
        use_backtest = VALUES(use_backtest),
        use_realtime = VALUES(use_realtime),
        use_replay = VALUES(use_replay)
    """
    conn.execute(text(insert_sql))
    conn.commit()

print('✅ 表 quant_screen_schemes 创建成功')
print('✅ 默认方案已插入')
