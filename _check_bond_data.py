import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

date = '20260731'
code = '123118'

with engine.connect() as conn:
    # 查询09:40:03的数据
    sql = text(f'''
        SELECT code, time, window_count 
        FROM monitor_zq_top30_{date} 
        WHERE code = '{code}' AND time = '09:40:03'
    ''')
    result = conn.execute(sql).fetchall()
    print('09:40:03 数据:')
    for row in result:
        print(f'  code={row[0]}, time={row[1]}, window_count={row[2]}')
    
    # 查询该债券在09:40区间的所有记录
    sql2 = text(f'''
        SELECT code, time, window_count 
        FROM monitor_zq_top30_{date} 
        WHERE code = '{code}' AND time >= '09:40:00' AND time < '09:50:00'
        ORDER BY time
    ''')
    result2 = conn.execute(sql2).fetchall()
    print(f'\\n09:40-09:50区间共{len(result2)}条记录:')
    for row in result2[:5]:
        print(f'  {row[1]}: window_count={row[2]}')
