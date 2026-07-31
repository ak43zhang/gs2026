"""
将MySQL的window_count数据同步到Redis/内存缓存
用于10分钟区间重算后的数据填充
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
from gs2026.utils import mysql_util
from gs2026.monitor import window_count_cache as wc_cache

def sync_mysql_to_cache(date_str: str, rank_type: str = 'stock'):
    """
    将MySQL的window_count同步到内存缓存
    
    Args:
        date_str: 日期 YYYYMMDD
        rank_type: 'stock' 或 'bond'
    """
    engine = mysql_util.get_mysql_engine()
    prefix = 'monitor_gp_top30' if rank_type == 'stock' else 'monitor_zq_top30'
    table_name = f"{prefix}_{date_str}"
    
    try:
        # 读取MySQL数据（只读需要的列）
        df = pd.read_sql(
            f"SELECT code, time, window_count FROM {table_name} WHERE window_count > 0", 
            engine
        )
        if df.empty:
            print(f"{table_name} 无window_count数据")
            return 0
        
        print(f"读取 {len(df)} 行window_count数据")
        
        # 填充到内存缓存
        count = 0
        for _, row in df.iterrows():
            code = str(row['code'])
            time_str = row['time']
            window_count = int(row['window_count'])
            
            # 计算区间起始
            window_start = wc_cache._calculate_window_start(time_str)
            
            # 直接写入缓存（不递增，用MySQL的值）
            key = (date_str, window_start, code)
            with wc_cache._cache_lock:
                wc_cache._window_count_cache[key] = window_count
            count += 1
        
        print(f"已同步 {count} 条到内存缓存")
        return count
        
    except Exception as e:
        print(f"同步失败: {e}")
        return 0

if __name__ == "__main__":
    import datetime
    import argparse
    
    parser = argparse.ArgumentParser(description='同步window_count到缓存')
    parser.add_argument('--date', default=datetime.datetime.now().strftime("%Y%m%d"),
                       help='日期 YYYYMMDD，默认今天')
    parser.add_argument('--type', default='stock', choices=['stock', 'bond'],
                       help='类型: stock 或 bond')
    args = parser.parse_args()
    
    print(f"开始同步 {args.date} {args.type} 的window_count...")
    n = sync_mysql_to_cache(args.date, args.type)
    print(f"完成，共同步 {n} 条")
