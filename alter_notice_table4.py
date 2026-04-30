import mysql.connector
import sys
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
        connect_timeout=10
    )
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("SHOW COLUMNS FROM analysis_notice_detail_2026 LIKE 'notice_category'")
    result = cursor.fetchall()
    if result:
        print(f'Column already exists: {result}')
    else:
        print('Column does not exist, adding...')
        sys.stdout.flush()
        cursor.execute("ALTER TABLE analysis_notice_detail_2026 ADD COLUMN notice_category VARCHAR(64) DEFAULT '' AFTER notice_type")
        conn.commit()
        print('SUCCESS - column added')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
