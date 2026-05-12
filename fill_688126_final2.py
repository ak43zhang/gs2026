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
    
    # 更新Redis - 使用不同的key避免类型冲突
    redis_client = redis_util._get_redis_client()
    redis_key = f'monitor_gp_sssj_20260512:{latest_time}:derived'  # 加:derived后缀
    field_key = '688126:max_cumulative_main_net'
    redis_client.hset(redis_key, field_key, str(peak))
    print(f'Redis更新完成: {redis_key}, field={field_key}, value={peak}')
    
    # 验证
    val = redis_client.hget(redis_key, field_key)
    print(f'Redis验证: {val}')
    
    # 同时更新到另一个key供前端使用
    redis_key2 = f'stock:688126:20260512:derived'
    redis_client.hset(redis_key2, 'max_cumulative_main_net', str(peak))
    print(f'Redis备用key: {redis_key2}')

print('完成!')
