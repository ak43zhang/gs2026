#!/usr/bin/env python3
"""
填充历史数据的累计主力净额
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from sqlalchemy import create_engine, text

DB_CONFIG = {
    'host': '192.168.0.101',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gs'
}

TABLE_NAME = "monitor_gp_sssj_20260428"


def get_engine():
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    return create_engine(url)


def fill_cumulative():
    """使用窗口函数填充累计值"""
    engine = get_engine()
    
    print(f"开始填充 {TABLE_NAME} 的累计主力净额")
    print("=" * 60)
    
    # 使用窗口函数计算累计值
    with engine.connect() as conn:
        # 先检查有多少记录需要更新
        result = conn.execute(text(f"""
            SELECT COUNT(*) 
            FROM {TABLE_NAME} 
            WHERE cumulative_main_net = 0 OR cumulative_main_net IS NULL
        """)).fetchone()
        
        print(f"需要更新的记录数: {result[0]:,}")
        print()
        
        # 分批处理（每批1000只股票）
        # 获取所有股票代码
        stocks = pd.read_sql(f"SELECT DISTINCT stock_code FROM {TABLE_NAME}", conn)
        stock_codes = stocks['stock_code'].tolist()
        
        print(f"共 {len(stock_codes)} 只股票需要处理")
        print()
        
        batch_size = 100
        total_batches = (len(stock_codes) + batch_size - 1) // batch_size
        total_updated = 0
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min((batch_idx + 1) * batch_size, len(stock_codes))
            batch_codes = stock_codes[start_idx:end_idx]
            codes_str = ','.join([f"'{c}'" for c in batch_codes])
            
            print(f"处理第 {batch_idx + 1}/{total_batches} 批 ({len(batch_codes)} 只股票)...", end=' ')
            
            try:
                # 使用窗口函数计算累计值并更新
                update_sql = f"""
                UPDATE {TABLE_NAME} t1
                JOIN (
                    SELECT 
                        stock_code,
                        time,
                        SUM(main_net_amount) OVER (
                            PARTITION BY stock_code 
                            ORDER BY time 
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) as calculated_cumulative
                    FROM {TABLE_NAME}
                    WHERE stock_code IN ({codes_str})
                ) t2 ON t1.stock_code = t2.stock_code AND t1.time = t2.time
                SET t1.cumulative_main_net = t2.calculated_cumulative
                """
                
                result = conn.execute(text(update_sql))
                conn.commit()
                
                # 统计更新数量
                count_result = conn.execute(text(f"""
                    SELECT COUNT(*) 
                    FROM {TABLE_NAME} 
                    WHERE stock_code IN ({codes_str})
                    AND cumulative_main_net != 0
                """)).fetchone()
                
                total_updated += count_result[0]
                print(f"更新 {count_result[0]} 条")
                
            except Exception as e:
                print(f"[ERROR] {e}")
                continue
        
        print()
        print("=" * 60)
        print(f"[OK] 完成！共更新 {total_updated} 条记录")
        
        # 验证
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as has_cumulative
            FROM {TABLE_NAME}
        """)).fetchone()
        
        print()
        print("验证结果:")
        print(f"  总记录数: {result[0]:,}")
        print(f"  有累计值: {result[1]:,} ({result[1]/result[0]*100:.2f}%)")


if __name__ == "__main__":
    fill_cumulative()
