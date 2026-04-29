import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root', password='123456', database='gs')
cursor = conn.cursor()
cursor.execute('SHOW COLUMNS FROM monitor_gp_top30_20260429')
for row in cursor.fetchall():
    print(row[0])
conn.close()
