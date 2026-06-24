"""
创建潜在标的挖掘记录表
- stock_anomaly_potential: 存储每次挖掘的潜在标的

用法:
    python scripts/create_potential_table.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import mysql.connector
from gs2026.utils import config_util


def get_connection():
    return mysql.connector.connect(
        host=config_util.get_config('mysql.host'),
        port=int(config_util.get_config('mysql.port')),
        user=config_util.get_config('mysql.user'),
        password=config_util.get_config('mysql.password'),
        database=config_util.get_config('mysql.database'),
        connection_timeout=10
    )


def create_table():
    conn = get_connection()
    cursor = conn.cursor()

    # 潜在标的挖掘记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_anomaly_potential (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trading_date DATE NOT NULL,
            trigger_time TIME NOT NULL,
            trigger_type VARCHAR(20),
            stock_code VARCHAR(10) NOT NULL,
            stock_name VARCHAR(50),
            rank_num INT,
            mainline_count INT,
            mainlines JSON,
            total_score INT,
            suggested_entry VARCHAR(100),
            risk_level VARCHAR(10),
            logic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_date_time_code (trading_date, trigger_time, stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 索引（MySQL 5.7不支持IF NOT EXISTS）
    try:
        cursor.execute("""
            CREATE INDEX idx_date_time 
            ON stock_anomaly_potential(trading_date, trigger_time)
        """)
    except Exception:
        pass  # 索引已存在

    try:
        cursor.execute("""
            CREATE INDEX idx_rank 
            ON stock_anomaly_potential(trading_date, trigger_time, rank_num)
        """)
    except Exception:
        pass  # 索引已存在

    conn.commit()
    cursor.close()
    conn.close()

    print("[OK] stock_anomaly_potential 表创建成功")


if __name__ == '__main__':
    create_table()
