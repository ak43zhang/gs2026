import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root', password='123456', database='gs')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*), SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END), SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) FROM monitor_gp_sssj_20260429')
row = cursor.fetchone()
print(f'Total: {row[0]:,}')
print(f'Main: {row[1]:,} ({row[1]/row[0]*100:.1f}%)')
print(f'Cum: {row[2]:,} ({row[2]/row[0]*100:.1f}%)')
conn.close()
