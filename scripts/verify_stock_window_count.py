"""
验证 monitor_gp_top30_YYYYMMDD 表的 window_count 字段

用法：
    python scripts/verify_stock_window_count.py 20260618
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import pandas as pd
import argparse

# 配置
url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def calculate_window_start(time_str, window_minutes=15):
    """计算15分钟区间起始"""
    hh, mm, ss = time_str.split(':')
    hour, minute = int(hh), int(mm)
    window_start = (minute // window_minutes) * window_minutes
    return f"{hour:02d}:{window_start:02d}:00"


def verify(date_str: str):
    """验证指定日期的股票排行表 window_count"""
    table_name = f'monitor_gp_top30_{date_str}'
    
    print(f"\n{'='*60}")
    print(f"验证表: {table_name}")
    print(f"{'='*60}\n")
    
    with engine.connect() as conn:
        # 1. 检查表是否存在
        check_sql = f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """
        result = conn.execute(text(check_sql))
        if result.scalar() == 0:
            print(f"❌ 表 {table_name} 不存在")
            return
        print(f"✓ 表 {table_name} 存在")
        
        # 2. 检查字段是否存在
        col_sql = f"""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}' 
            AND column_name = 'window_count'
        """
        result = conn.execute(text(col_sql))
        has_field = result.scalar() > 0
        if not has_field:
            print(f"❌ window_count 字段不存在")
            return
        print(f"✓ window_count 字段存在")
        
        # 3. 获取数据统计
        stats_sql = f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT code) as total_codes,
                MIN(time) as min_time,
                MAX(time) as max_time,
                MAX(window_count) as max_wc
            FROM {table_name}
        """
        stats_df = pd.read_sql(stats_sql, conn)
        print(f"\n数据统计:")
        print(f"  总行数: {stats_df.iloc[0]['total_rows']}")
        print(f"  不同股票数: {stats_df.iloc[0]['total_codes']}")
        print(f"  时间范围: {stats_df.iloc[0]['min_time']} ~ {stats_df.iloc[0]['max_time']}")
        print(f"  最大window_count: {stats_df.iloc[0]['max_wc']}")
        
        # 4. 抽查几个时间点的数据
        print(f"\n抽查数据（09:45:00 左右）:")
        sample_sql = f"""
            SELECT time, code, name, window_count
            FROM {table_name}
            WHERE time BETWEEN '09:44:50' AND '09:45:10'
            ORDER BY time, code
            LIMIT 20
        """
        sample_df = pd.read_sql(sample_sql, conn)
        if not sample_df.empty:
            print(sample_df.to_string(index=False))
        else:
            print("  该时间段无数据")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证股票排行 window_count')
    parser.add_argument('date', help='日期，如 20260618')
    args = parser.parse_args()
    
    verify(args.date)
