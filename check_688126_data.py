import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text

# 初始化
tool = mysql_util.get_mysql_tool()
redis_util.init_redis()

print('=== 1. 检查MySQL中688126的数据 ===')
with tool.engine.connect() as conn:
    # 检查字段是否存在
    sql1 = "SHOW COLUMNS FROM monitor_gp_sssj_20260512 LIKE 'cumulative_main_net'"
    result = conn.execute(text(sql1))
    cols = result.fetchall()
    print(f'cumulative_main_net字段存在: {len(cols) > 0}')
    
    sql2 = "SHOW COLUMNS FROM monitor_gp_sssj_20260512 LIKE 'max_cumulative_main_net'"
    result = conn.execute(text(sql2))
    cols = result.fetchall()
    print(f'max_cumulative_main_net字段存在: {len(cols) > 0}')
    
    # 获取688126的最新记录
    sql3 = "SELECT stock_code, cumulative_main_net, max_cumulative_main_net FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY time DESC LIMIT 1"
    result = conn.execute(text(sql3))
    row = result.fetchone()
    if row:
        print(f'最新记录: stock_code={row[0]}, cumulative={row[1]}, max={row[2]}')
    else:
        print('未找到688126的记录')

print()
print('=== 2. 检查Redis中688126的数据 ===')
redis_client = redis_util._get_redis_client()

# 检查Redis key
for key_pattern in ['monitor_gp_sssj_20260512:15:00:00', 'monitor_gp_sssj_20260512:14:56:45']:
    print(f'Key pattern: {key_pattern}')
    keys = redis_client.keys(f'{key_pattern}*')
    for k in keys[:3]:
        k_str = k.decode() if isinstance(k, bytes) else k
        print(f'  找到key: {k_str}')
        # 检查类型
        key_type = redis_client.type(k_str)
        print(f'    类型: {key_type}')
        if key_type == b'hash':
            val = redis_client.hget(k_str, '688126:cumulative_main_net')
            print(f'    688126:cumulative_main_net = {val}')
            val2 = redis_client.hget(k_str, '688126:max_cumulative_main_net')
            print(f'    688126:max_cumulative_main_net = {val2}')
