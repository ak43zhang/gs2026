"""
排查债券排行区间次数显示问题
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 检查今天的债券表
today = datetime.now().strftime('%Y%m%d')
table_today = f'monitor_zq_top30_{today}'
table_0618 = 'monitor_zq_top30_20260618'

def check_table(table_name):
    print(f"\n=== 检查表: {table_name} ===")
    
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
        
        # 2. 检查字段
        col_sql = f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """
        result = conn.execute(text(col_sql))
        cols = [row[0] for row in result]
        print(f"字段列表: {cols}")
        
        # 3. 检查数据量
        count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
        result = conn.execute(text(count_sql))
        total = result.scalar()
        print(f"总记录数: {total}")
        
        # 4. 检查window_count分布
        if 'window_count' in cols:
            dist_sql = f"""
                SELECT 
                    SUM(CASE WHEN window_count = 0 THEN 1 ELSE 0 END) as zero_count,
                    SUM(CASE WHEN window_count > 0 THEN 1 ELSE 0 END) as positive_count,
                    MAX(window_count) as max_val,
                    MIN(window_count) as min_val
                FROM {table_name}
            """
            result = conn.execute(text(dist_sql))
            row = result.fetchone()
            print(f"\nwindow_count分布:")
            print(f"  为0的记录: {row[0]}")
            print(f"  大于0的记录: {row[1]}")
            print(f"  最大值: {row[2]}")
            print(f"  最小值: {row[3]}")
            
            # 5. 查看样本数据
            if total > 0:
                sample_sql = f"""
                    SELECT code, name, time, window_count 
                    FROM {table_name} 
                    ORDER BY time DESC 
                    LIMIT 10
                """
                sample = pd.read_sql(sample_sql, conn)
                print(f"\n最新10条样本:")
                print(sample.to_string(index=False))
        else:
            print("window_count 字段不存在!")

check_table(table_0618)
check_table(table_today)
