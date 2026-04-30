import mysql.connector
import sys
import traceback
print('Starting...')
sys.stdout.flush()
try:
    conn = mysql.connector.connect(
        host='192.168.0.101',
        port=3306,
        user='root',
        password='123456',
        database='gs',
        charset='utf8',
        connect_timeout=30,
        connection_timeout=30
    )
    cursor = conn.cursor()
    print('Executing ALTER...')
    sys.stdout.flush()
    cursor.execute("ALTER TABLE analysis_notice_detail_2026 ADD COLUMN notice_category VARCHAR(64) DEFAULT ''")
    print('Committing...')
    sys.stdout.flush()
    conn.commit()
    print('SUCCESS')
    cursor.close()
    conn.close()
except BaseException as e:
    traceback.print_exc()
    print(f'ERROR: {type(e).__name__}: {e}')
    sys.exit(1)
