import mysql.connector
import sys

try:
    conn = mysql.connector.connect(
        host='192.168.0.101',
        port=3306,
        user='root',
        password='123456',
        database='gs',
        charset='utf8'
    )
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE analysis_notice_detail_2026 ADD COLUMN notice_category VARCHAR(64) DEFAULT '' COMMENT '公告类型分类' AFTER notice_type")
    conn.commit()
    print('SUCCESS')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
