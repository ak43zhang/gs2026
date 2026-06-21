"""
重新回填 monitor_zq_top30_20260618 表的 window_count 字段（使用新逻辑）
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import pandas as pd

# 配置
url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

table_name = 'monitor_zq_top30_20260618'
date_str = '20260618'

def calculate_window_start(time_str):
    """计算15分钟区间起始"""
    hh, mm, _ = time_str.split(':')
    hour, minute = int(hh), int(mm)
    return f"{hour:02d}:{(minute // 15) * 15:02d}:00"

def backfill_with_new_logic():
    """使用新逻辑回填：模拟内存缓存+数据库恢复"""
    
    # 1. 读取数据按时间排序
    with engine.connect() as conn:
        df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY time, code", conn)
    
    if df.empty:
        print("表为空")
        return
    
    print(f"读取到 {len(df)} 条记录")
    
    # 2. 模拟新方案：内存缓存递增
    window_cache = {}  # {(date, window_start, code): count}
    updates = []
    
    for idx, row in df.iterrows():
        code = str(row['code'])
        time_str = str(row['time'])
        window_start = calculate_window_start(time_str)
        key = (date_str, window_start, code)
        
        # 内存递增（模拟新方案）
        current = window_cache.get(key, 0)
        window_cache[key] = current + 1
        window_count = current + 1
        
        updates.append({
            'code': code,
            'time': time_str,
            'window_count': window_count
        })
    
    print(f"计算出 {len(updates)} 条 window_count")
    
    # 3. 清空并重新写入
    with engine.connect() as conn:
        # 先重置为0
        conn.execute(text(f"UPDATE {table_name} SET window_count = 0"))
        conn.commit()
        
        # 再更新
        for update in updates:
            sql = f"""
                UPDATE {table_name} 
                SET window_count = {update['window_count']}
                WHERE code = '{update['code']}' AND time = '{update['time']}'
            """
            conn.execute(text(sql))
        conn.commit()
    
    print(f"回填完成")
    
    # 4. 验证
    with engine.connect() as conn:
        verify_df = pd.read_sql(
            f"SELECT code, name, time, window_count FROM {table_name} WHERE window_count > 0 ORDER BY time DESC, window_count DESC LIMIT 20", 
            conn
        )
        print("\n验证数据（前20条）：")
        print(verify_df.to_string(index=False))
        
        # 统计
        stats = pd.read_sql(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN window_count > 0 THEN 1 ELSE 0 END) as filled,
                MAX(window_count) as max_count,
                AVG(window_count) as avg_count
            FROM {table_name}
        """, conn)
        print("\n统计信息：")
        print(stats.to_string(index=False))

if __name__ == '__main__':
    backfill_with_new_logic()
