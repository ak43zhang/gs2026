import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text

# 初始化
tool = mysql_util.get_mysql_tool()
redis_util.init_redis()

with tool.engine.connect() as conn:
    # 获取688126的峰值
    result = conn.execute(text("SELECT MAX(cumulative_main_net) FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126'"))
    peak = result.fetchone()[0] or 0
    print(f'688126峰值: {peak}')
    
    # 更新所有记录的max_cumulative_main_net
    result = conn.execute(text(f"UPDATE monitor_gp_sssj_20260512 SET max_cumulative_main_net = {peak} WHERE stock_code = '688126'"))
    conn.commit()
    print(f'MySQL更新完成: {result.rowcount}条')
    
    # 获取最新的time
    result = conn.execute(text("SELECT time FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY time DESC LIMIT 1"))
    latest_time = result.fetchone()[0]
    print(f'最新时间: {latest_time}')
    
    # 更新Redis
    # Redis key格式: monitor_gp_sssj_20260512:{time}
    redis_key = f'monitor_gp_sssj_20260512:{latest_time}'
    redis_util.hset(redis_key, '688126:max_cumulative_main_net', str(peak))
    print(f'Redis更新完成: {redis_key}')
    
    # 同时更新到DataFrame缓存
    df_key = f'monitor_gp_sssj_20260512:{latest_time}'
    print(f'DataFrame key: {df_key}')

print('完成!')
