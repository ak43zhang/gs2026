"""
填充688126的max_cumulative_main_net数据用于测试
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text

date_str = '20260512'
table_name = 'monitor_gp_sssj_20260512'
stock_code = '688126'

def fill_max_cumulative():
    # 初始化
    tool = mysql_util.get_mysql_tool()
    redis_util.init_redis()
    
    with tool.engine.connect() as conn:
        # 检查字段是否存在
        result = conn.execute(text("SHOW COLUMNS FROM monitor_gp_sssj_20260512 LIKE 'max_cumulative_main_net'"))
        rows = result.fetchall()
        print(f'字段存在: {len(rows) > 0}')
        
        if not rows:
            print('添加字段...')
            conn.execute(text("ALTER TABLE monitor_gp_sssj_20260512 ADD COLUMN max_cumulative_main_net FLOAT DEFAULT 0"))
            conn.commit()
        
        # 获取688126的所有数据
        result = conn.execute(text(f"SELECT time_str, cumulative_main_net FROM {table_name} WHERE stock_code = '{stock_code}' ORDER BY time_str ASC"))
        rows = result.fetchall()
        print(f'找到{len(rows)}条记录')
        
        if not rows:
            print(f'未找到{stock_code}的数据')
            return
        
        # 计算max_cumulative_main_net
        max_val = 0
        updates = []
        
        for time_str, cum_val in rows:
            cum_val = cum_val or 0
            max_val = max(max_val, cum_val)
            updates.append((max_val, time_str))
        
        print(f'峰值: {max_val}')
        
        # 更新MySQL
        for max_v, t_str in updates:
            conn.execute(text(f"UPDATE {table_name} SET max_cumulative_main_net = {max_v} WHERE time_str = '{t_str}' AND stock_code = '{stock_code}'"))
        
        conn.commit()
        print(f'MySQL更新完成: {len(updates)}条')
        
        # 更新Redis
        latest_time = rows[-1][0]
        redis_key = f"monitor_gp_sssj_{date_str}:{latest_time}"
        redis_util.hset(redis_key, f"{stock_code}:max_cumulative_main_net", str(max_val))
        print(f'Redis更新完成: key={redis_key}, max={max_val}')
    
    print('完成!')

if __name__ == '__main__':
    fill_max_cumulative()
