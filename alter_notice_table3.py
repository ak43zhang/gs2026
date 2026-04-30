import mysql.connector
import sys
print('Starting...')
sys.stdout.flush()
try:
    print('Connecting...')
    sys.stdout.flush()
    conn = mysql.connector.connect(
        host='192.168.0.101',
        port=3306,
        user='root',
        password='123456',
        database='gs',
        charset='utf8',
        connect_timeout=10
    )
    print('Connected')
    sys.stdout.flush()
    cursor = conn.cursor()
    sql = "ALTER TABLE analysis_notice_detail_2026 ADD COLUMN notice_category VARCHAR(64) DEFAULT '' AFTER notice_type"
    print(f'Executing: {sql[:60]}...')
    sys.stdout.flush()
    cursor.execute(sql)
    conn.commit()
    print('SUCCESS')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
    sys.exit(1)
