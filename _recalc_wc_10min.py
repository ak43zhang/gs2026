"""
重新计算 window_count（10分钟区间）
用于窗口时间从15分钟改为10分钟后的数据重填
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util, mysql_util

def recalculate_window_count(date_str: str):
    """重新计算指定日期的 window_count"""
    engine = mysql_util.get_mysql_engine()
    
    # 获取当天的 gp_top30 数据
    table_name = f"monitor_gp_top30_{date_str}"
    
    try:
        # 读取原始数据
        df = pd.read_sql(f"SELECT * FROM {table_name} ORDER BY time, code", engine)
        if df.empty:
            print(f"{table_name} 为空，跳过")
            return
        
        print(f"读取 {len(df)} 行数据")
        
        # 按 code 分组，计算10分钟区间次数
        def calc_window_count_10min(group):
            group = group.sort_values('time')
            # 计算10分钟区间起始
            group['window_start'] = group['time'].apply(
                lambda t: f"{t[:2]}:{int(t[3:5])//10*10:02d}:00"
            )
            # 按 window_start 分组计数（累积）
            group['window_count'] = group.groupby('window_start').cumcount() + 1
            return group
        
        df = df.groupby('code', group_keys=False).apply(calc_window_count_10min)
        
        # 写回数据库
        with engine.connect() as conn:
            for _, row in df.iterrows():
                conn.execute(text(f"""
                    UPDATE {table_name} 
                    SET window_count = {row['window_count']}
                    WHERE code = '{row['code']}' AND time = '{row['time']}'
                """))
            conn.commit()
        
        print(f"更新完成: {table_name}")
        
    except Exception as e:
        print(f"处理 {table_name} 失败: {e}")

if __name__ == "__main__":
    import datetime
    today = datetime.datetime.now().strftime("%Y%m%d")
    recalculate_window_count(today)
