import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root', password='123456', database='gs')
cursor = conn.cursor()

# 已填充的股票数量
cursor.execute('SELECT COUNT(DISTINCT stock_code) FROM monitor_gp_sssj_20260429 WHERE main_net_amount != 0')
filled_stocks = cursor.fetchone()[0]

# 已填充的记录数
cursor.execute('SELECT COUNT(*) FROM monitor_gp_sssj_20260429 WHERE main_net_amount != 0')
filled_records = cursor.fetchone()[0]

# 总记录数
cursor.execute('SELECT COUNT(*) FROM monitor_gp_sssj_20260429')
total_records = cursor.fetchone()[0]

print(f'已填充股票: {filled_stocks} 只')
print(f'已填充记录: {filled_records:,} / {total_records:,} ({filled_records/total_records*100:.2f}%)')

# Top 10股票
cursor.execute('''
    SELECT stock_code, short_name, MAX(cumulative_main_net) 
    FROM monitor_gp_sssj_20260429 
    WHERE main_net_amount != 0 
    GROUP BY stock_code, short_name 
    ORDER BY ABS(MAX(cumulative_main_net)) DESC 
    LIMIT 10
''')

print('\nTop 10 累计主力净额:')
for i, row in enumerate(cursor.fetchall(), 1):
    print(f'  {i}. {row[0]} {row[1]}: {row[2]:,.0f}')

conn.close()
