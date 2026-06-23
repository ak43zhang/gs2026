"""添加预期属性字段到领域分析和新闻分析表"""
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

alterations = [
    ("analysis_domain_detail_2026", "expectation_type", 
     "ALTER TABLE analysis_domain_detail_2026 ADD COLUMN expectation_type VARCHAR(20) DEFAULT NULL COMMENT '预期属性'"),
    ("analysis_domain_detail_2026", "expectation_analysis",
     "ALTER TABLE analysis_domain_detail_2026 ADD COLUMN expectation_analysis VARCHAR(500) DEFAULT NULL COMMENT '预期分析'"),
    ("analysis_news_detail_2026", "expectation_type",
     "ALTER TABLE analysis_news_detail_2026 ADD COLUMN expectation_type VARCHAR(20) DEFAULT NULL COMMENT '预期属性'"),
    ("analysis_news_detail_2026", "expectation_analysis",
     "ALTER TABLE analysis_news_detail_2026 ADD COLUMN expectation_analysis VARCHAR(500) DEFAULT NULL COMMENT '预期分析'"),
]

for table, col, sql in alterations:
    try:
        cursor.execute(sql)
        conn.commit()
        print(f'✓ {table}.{col} 添加成功')
    except mysql.connector.Error as e:
        if e.errno == 1060:  # Duplicate column
            print(f'- {table}.{col} 已存在，跳过')
        else:
            print(f'✗ {table}.{col} 添加失败: {e}')

cursor.close()
conn.close()
print('\n完成')
