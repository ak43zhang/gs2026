"""
检查并回填 monitor_zq_top30_20260618 表的 window_count 字段
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util, mysql_util
from sqlalchemy import create_engine, text
import pandas as pd

# 配置
url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

table_name = 'monitor_zq_top30_20260618'
date_str = '20260618'

def calculate_window_start(time_str, window_minutes=15):
    """计算15分钟区间起始"""
    hh, mm, ss = time_str.split(':')
    hour, minute = int(hh), int(mm)
    window_start = (minute // 15) * 15
    return f"{hour:02d}:{window_start:02d}:00"

def check_and_backfill():
    """检查并回填"""
    
    # 1. 检查表是否存在
    with engine.connect() as conn:
        check_sql = f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """
        result = conn.execute(text(check_sql))
        if result.scalar() == 0:
            print(f"表 {table_name} 不存在")
            return
        print(f"表 {table_name} 存在")
        
        # 2. 检查字段是否存在
        col_sql = f"""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}' AND column_name = 'window_count'
        """
        result = conn.execute(text(col_sql))
        has_field = result.scalar() > 0
        print(f"window_count 字段: {'已存在' if has_field else '不存在'}")
        
        if not has_field:
            # 添加字段
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN window_count INT DEFAULT 0"
            conn.execute(text(alter_sql))
            conn.commit()
            print(f"已添加 window_count 字段")
    
    # 3. 读取数据
    with engine.connect() as conn:
        df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY time, code", conn)
    
    if df.empty:
        print("表为空，无需回填")
        return
    
    print(f"读取到 {len(df)} 条记录")
    
    # 4. 计算 window_count
    window_cache = {}
    updates = []
    
    for idx, row in df.iterrows():
        code = str(row['code'])
        time_str = str(row['time'])
        window_start = calculate_window_start(time_str)
        key = (date_str, window_start, code)
        
        current = window_cache.get(key, 0)
        window_cache[key] = current + 1
        window_count = current + 1
        
        updates.append({
            'code': code,
            'time': time_str,
            'window_count': window_count
        })
    
    print(f"计算出 {len(updates)} 条 window_count")
    
    # 5. 更新数据库
    with engine.connect() as conn:
        for update in updates:
            sql = f"""
                UPDATE {table_name} 
                SET window_count = {update['window_count']}
                WHERE code = '{update['code']}' AND time = '{update['time']}'
            """
            conn.execute(text(sql))
        conn.commit()
    
    print(f"回填完成")
    
    # 6. 验证
    with engine.connect() as conn:
        verify_df = pd.read_sql(
            f"SELECT code, name, time, window_count FROM {table_name} WHERE window_count > 0 ORDER BY time DESC, window_count DESC LIMIT 20", 
            conn
        )
        print("\n验证数据（前20条window_count>0）：")
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
        
        # 查看区间分布
        dist = pd.read_sql(f"""
            SELECT window_count, COUNT(*) as cnt
            FROM {table_name}
            WHERE window_count > 0
            GROUP BY window_count
            ORDER BY window_count DESC
            LIMIT 10
        """, conn)
        print("\n区间次数分布（TOP10）：")
        print(dist.to_string(index=False))

if __name__ == '__main__':
    check_and_backfill()
