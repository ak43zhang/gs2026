import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
os.chdir(r'F:\pyworkspace2026\gs2026')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text

# 从配置读取
from gs2026.utils import config_util
_config = config_util.load_config()
_mysql_config = _config.get('mysql', {})
host = _mysql_config.get('host', '192.168.0.101')
port = _mysql_config.get('port', 3306)
user = _mysql_config.get('user', 'root')
password = _mysql_config.get('password', '123456')
database = _mysql_config.get('database', 'gs')

uri = f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4'
print(f'连接: {host}:{port}/{database}')

engine = create_engine(uri)

sql = """
CREATE TABLE IF NOT EXISTS buy_point_candidates (
    id                  BIGINT PRIMARY KEY AUTO_INCREMENT,
    date                DATE NOT NULL,
    time                TIME NOT NULL,
    stock_code          VARCHAR(10) NOT NULL,
    stock_name          VARCHAR(50),
    stock_price         DECIMAL(10,2),
    stock_change_pct    DECIMAL(5,2),
    bond_code           VARCHAR(10),
    bond_price          DECIMAL(10,2),
    bond_change_pct     DECIMAL(5,2),
    level               TINYINT,
    condition_count     TINYINT,
    total_conditions    TINYINT,
    conditions          JSON,
    market_context      JSON,
    result_5m_price     DECIMAL(10,2),
    result_5m_change    DECIMAL(5,2),
    result_15m_price    DECIMAL(10,2),
    result_15m_change   DECIMAL(5,2),
    result_30m_price    DECIMAL(10,2),
    result_30m_change   DECIMAL(5,2),
    result_close_price  DECIMAL(10,2),
    result_close_change DECIMAL(5,2),
    is_success_5m       BOOLEAN,
    is_success_15m      BOOLEAN,
    is_success_30m      BOOLEAN,
    is_success_close    BOOLEAN,
    is_valid            BOOLEAN DEFAULT TRUE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_date_time (date, time),
    INDEX idx_stock_code (stock_code),
    INDEX idx_bond_code (bond_code),
    INDEX idx_level (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='买点候选记录表'
"""

try:
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print('✅ buy_point_candidates 表创建成功')
except Exception as e:
    print(f'❌ 错误: {e}')
