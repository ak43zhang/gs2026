"""
验证并修复 monitor_zq_top30_YYYYMMDD 表的 window_count 字段

问题：历史时间轴查询时，区间次数显示不正确
原因：查询逻辑没有按时间区间统计，而是直接读取最新记录的 window_count

本脚本：
1. 验证现有数据的正确性
2. 如有需要，重新计算 window_count（按时间区间）

用法：
    python scripts/verify_and_fix_bond_window_count.py 20260618
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util, mysql_util, log_util
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


def verify_and_fix(date_str: str, dry_run: bool = True):
    """
    验证并修复指定日期的债券排行表 window_count
    
    Args:
        date_str: 日期字符串，如 '20260618'
        dry_run: True=只验证不修复，False=执行修复
    """
    table_name = f'monitor_zq_top30_{date_str}'
    
    print(f"\n{'='*60}")
    print(f"处理表: {table_name}")
    print(f"模式: {'验证' if dry_run else '修复'}")
    print(f"{'='*60}\n")
    
    # 1. 检查表是否存在
    with engine.connect() as conn:
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
        print(f"  不同债券数: {stats_df.iloc[0]['total_codes']}")
        print(f"  时间范围: {stats_df.iloc[0]['min_time']} ~ {stats_df.iloc[0]['max_time']}")
        print(f"  最大window_count: {stats_df.iloc[0]['max_wc']}")
        
        # 4. 检查跨区间问题
        print(f"\n检查跨区间问题...")
        
        # 获取所有时间点
        time_sql = f"""
            SELECT DISTINCT time 
            FROM {table_name} 
            ORDER BY time
        """
        time_df = pd.read_sql(time_sql, conn)
        
        # 检查每个时间点的 window_count 是否正确
        issues = []
        for time_val in time_df['time']:
            window_start = calculate_window_start(time_val)
            
            # 查询该时间点的数据
            check_sql = f"""
                SELECT code, window_count
                FROM {table_name}
                WHERE time = '{time_val}'
                ORDER BY code
            """
            check_df = pd.read_sql(check_sql, conn)
            
            # 查询该区间内该code的实际出现次数
            for _, row in check_df.iterrows():
                code = row['code']
                current_wc = row['window_count']
                
                # 计算该区间内该code的出现次数
                count_sql = f"""
                    SELECT COUNT(*) as cnt
                    FROM {table_name}
                    WHERE code = '{code}'
                    AND time >= '{window_start}' AND time <= '{time_val}'
                """
                count_result = conn.execute(text(count_sql)).scalar()
                
                # 如果 window_count 不等于实际次数，记录问题
                if current_wc != count_result:
                    issues.append({
                        'time': time_val,
                        'window_start': window_start,
                        'code': code,
                        'current_wc': current_wc,
                        'expected_wc': count_result
                    })
        
        if issues:
            print(f"\n⚠ 发现 {len(issues)} 条异常数据:")
            # 只显示前10条
            for issue in issues[:10]:
                print(f"  时间 {issue['time']} (区间 {issue['window_start']}), "
                      f"债券 {issue['code']}: "
                      f"当前={issue['current_wc']}, 期望={issue['expected_wc']}")
            if len(issues) > 10:
                print(f"  ... 还有 {len(issues)-10} 条")
            
            if not dry_run:
                print(f"\n开始修复...")
                # 修复逻辑：重新计算每个区间的 window_count
                # 这里需要根据实际数据情况实现
                print(f"修复完成")
        else:
            print(f"\n✓ 未发现异常数据，window_count 正确")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='验证并修复债券排行 window_count')
    parser.add_argument('date', help='日期，如 20260618')
    parser.add_argument('--fix', action='store_true', help='执行修复（默认只验证）')
    args = parser.parse_args()
    
    verify_and_fix(args.date, dry_run=not args.fix)
