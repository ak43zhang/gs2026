"""添加 stock_anomaly 表索引优化查询性能"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import mysql.connector
from gs2026.utils import config_util

host = config_util.get_config('mysql.host')
port = config_util.get_config('mysql.port')
user = config_util.get_config('mysql.user')
password = config_util.get_config('mysql.password')
database = config_util.get_config('mysql.database')

conn = mysql.connector.connect(
    host=host, port=port, user=user, password=password, database=database
)
cursor = conn.cursor()

indexes = [
    ("idx_anomaly_date_time", "ALTER TABLE stock_anomaly ADD INDEX idx_anomaly_date_time (trading_date, anomaly_time DESC)"),
    ("idx_anomaly_date_status", "ALTER TABLE stock_anomaly ADD INDEX idx_anomaly_date_status (trading_date, ai_status)"),
]

for idx_name, sql in indexes:
    try:
        cursor.execute(sql)
        conn.commit()
        print(f'✓ 索引 {idx_name} 创建成功')
    except mysql.connector.Error as e:
        if e.errno == 1061:  # Duplicate key name
            print(f'- 索引 {idx_name} 已存在，跳过')
        else:
            print(f'✗ 索引 {idx_name} 创建失败: {e}')

cursor.close()
conn.close()
print('\n完成')
