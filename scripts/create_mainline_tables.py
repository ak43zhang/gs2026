"""
创建盘中异动主线分析相关表
- stock_anomaly_mainline: 市场主线表
- stock_anomaly_mainline_rel: 股票-主线多对多关系表
- ALTER stock_anomaly: 新增 mainline_names, correlation_context 字段
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


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 市场主线表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_anomaly_mainline (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trading_date DATE NOT NULL,
            mainline_id VARCHAR(32) NOT NULL COMMENT '主线MD5标识(name+date)',
            mainline_name VARCHAR(100) NOT NULL COMMENT '主线名称',
            mainline_reason TEXT COMMENT '主线驱动逻辑',
            catalyst VARCHAR(500) COMMENT '催化事件',
            related_stocks JSON COMMENT '关联股票[{"code","name","time","role"}]',
            confidence TINYINT DEFAULT 0 COMMENT '置信度1-100',
            stock_count INT DEFAULT 0 COMMENT '命中股票数',
            first_seen_time TIME COMMENT '首次识别时间',
            last_updated_time TIME COMMENT '最后更新时间',
            status VARCHAR(20) DEFAULT 'active' COMMENT 'active/merged/dismissed',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_mainline (trading_date, mainline_id),
            KEY idx_date_status (trading_date, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='盘中异动市场主线表'
    """)
    print("✅ stock_anomaly_mainline 表创建成功")

    # 2. 股票-主线多对多关系表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_anomaly_mainline_rel (
            id INT AUTO_INCREMENT PRIMARY KEY,
            anomaly_id INT NOT NULL COMMENT '关联stock_anomaly.id',
            mainline_id VARCHAR(32) NOT NULL COMMENT '关联主线标识',
            role VARCHAR(20) COMMENT '龙头/跟风/补涨',
            evidence VARCHAR(500) COMMENT '归属证据',
            confidence_contribution TINYINT DEFAULT 0 COMMENT '对主线置信度贡献',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            KEY idx_anomaly (anomaly_id),
            KEY idx_mainline (mainline_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票-主线多对多关系表'
    """)
    print("✅ stock_anomaly_mainline_rel 表创建成功")

    # 3. stock_anomaly 表新增字段
    # 先检查字段是否已存在
    cursor.execute("SHOW COLUMNS FROM stock_anomaly LIKE 'mainline_names'")
    if not cursor.fetchone():
        cursor.execute("""
            ALTER TABLE stock_anomaly
            ADD COLUMN mainline_names JSON DEFAULT NULL COMMENT '归属主线名称["主线1","主线2"]'
        """)
        print("✅ stock_anomaly.mainline_names 字段添加成功")
    else:
        print("⏭️ stock_anomaly.mainline_names 字段已存在")

    cursor.execute("SHOW COLUMNS FROM stock_anomaly LIKE 'correlation_context'")
    if not cursor.fetchone():
        cursor.execute("""
            ALTER TABLE stock_anomaly
            ADD COLUMN correlation_context TEXT DEFAULT NULL COMMENT '增量分析时上下文摘要'
        """)
        print("✅ stock_anomaly.correlation_context 字段添加成功")
    else:
        print("⏭️ stock_anomaly.correlation_context 字段已存在")

    conn.commit()
    cursor.close()
    conn.close()
    print("\n🎉 所有表和字段创建完成！")


if __name__ == '__main__':
    create_tables()
