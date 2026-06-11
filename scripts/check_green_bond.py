import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
import pymysql

conn = pymysql.connect(host='192.168.0.101', port=3306, user='root', password='123456', database='gs', connect_timeout=10)
cur = conn.cursor()

# Check if green_bond_list table exists
cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='gs' AND TABLE_NAME='green_bond_list'")
result = cur.fetchone()
print(f'Table exists: {bool(result)}')

if result:
    # Check columns
    cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='gs' AND TABLE_NAME='green_bond_list'")
    columns = [r[0] for r in cur.fetchall()]
    print(f'Columns: {columns}')
    
    # Check sample data
    cur.execute("SELECT * FROM green_bond_list LIMIT 5")
    rows = cur.fetchall()
    print(f'Sample rows: {len(rows)}')
    for r in rows:
        print(r)

conn.close()
