import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text

# 初始化
tool = mysql_util.get_mysql_tool()
redis_util.init_redis()

with tool.engine.connect() as conn:
    # 获取表结构
    result = conn.execute(text("SHOW COLUMNS FROM monitor_gp_sssj_20260512"))
    cols = [r[0] for r in result.fetchall()]
    print(f'字段: {cols[:10]}...')  # 只打印前10个
    
    # 获取688126的最新记录
    result = conn.execute(text("SELECT * FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY id DESC LIMIT 1"))
    row = result.fetchone()
    if row:
        print(f'最新记录id: {row[0]}')
        print(f'stock_code: {row[1]}')
        print(f'cumulative_main_net: {row[cols.index("cumulative_main_net")] if "cumulative_main_net" in cols else "N/A"}')
    
    # 获取峰值
    result = conn.execute(text("SELECT MAX(cumulative_main_net) FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126'"))
    peak = result.fetchone()[0] or 0
    print(f'688126峰值: {peak}')
    
    # 更新所有记录的max_cumulative_main_net
    result = conn.execute(text(f"UPDATE monitor_gp_sssj_20260512 SET max_cumulative_main_net = {peak} WHERE stock_code = '688126'"))
    conn.commit()
    print(f'MySQL更新完成: {result.rowcount}条')
    
    # 更新Redis - 使用最新的那条
    result = conn.execute(text("SELECT id FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126' ORDER BY id DESC LIMIT 1"))
    latest_id = result.fetchone()[0]
    
    # Redis key格式: monitor_gp_sssj_20260512:{time_str} 或直接用id
    # 先找到对应的Redis key
    redis_key = f'monitor_gp_sssj_20260512:14:56:45'  # 假设收盘时间
    
    # 尝试直接设置
    redis_util.hset(f'monitor_gp_sssj_20260512:test', '688126:max_cumulative_main_net', str(peak))
    print(f'Redis测试写入完成')
    
    # 获取实际的最新时间
    result = conn.execute(text("SELECT MAX(id) as max_id FROM monitor_gp_sssj_20260512 WHERE stock_code = '688126'"))
    max_id = result.fetchone()[0]
    print(f'最大id: {max_id}')

print('完成!')
