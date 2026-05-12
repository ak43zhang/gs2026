import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text

# 初始化
tool = mysql_util.get_mysql_tool()
redis_util.init_redis()

with tool.engine.connect() as conn:
    # 获取688126的峰值
    sql1 = "SELECT MAX(cumulative_main_net) FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126'"
    result = conn.execute(text(sql1))
    peak = result.fetchone()[0] or 0
    print(f'688126 peak: {peak}')
    
    # 获取最新时间
    sql2 = "SELECT time_str FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY time_str DESC LIMIT 1"
    result = conn.execute(text(sql2))
    latest_time = result.fetchone()[0]
    print(f'latest time: {latest_time}')
    
    # 更新MySQL
    sql3 = f"UPDATE monitor_gp_sssj_20260512 SET max_cumulative_main_net = {peak} WHERE stock_code = '688126'"
    conn.execute(text(sql3))
    conn.commit()
    print('MySQL updated')
    
    # 更新Redis
    redis_key = f'monitor_gp_sssj_20260512:{latest_time}'
    redis_util.hset(redis_key, '688126:max_cumulative_main_net', str(peak))
    print(f'Redis updated: {redis_key}')
    
print('Done!')
