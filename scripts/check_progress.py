#!/usr/bin/env python3
"""
检查主力净额填充进度
"""

from sqlalchemy import create_engine, text

DB_CONFIG = {
    'host': '192.168.0.101',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gs'
}

def check_progress():
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        # 检查总记录数
        total = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260428")).scalar()
        
        # 检查已填充的记录数
        filled = conn.execute(text("""
            SELECT COUNT(*) FROM monitor_gp_sssj_20260428 
            WHERE main_net_amount != 0 OR main_behavior != ''
        """)).scalar()
        
        # 检查有主力参与的记录数
        has_main = conn.execute(text("""
            SELECT COUNT(*) FROM monitor_gp_sssj_20260428 
            WHERE main_net_amount != 0
        """)).scalar()
        
        print(f"总记录数: {total:,}")
        print(f"已填充记录: {filled:,} ({filled/total*100:.1f}%)")
        print(f"有主力参与的记录: {has_main:,} ({has_main/total*100:.1f}%)")
        
        # 显示最近更新的股票
        recent = conn.execute(text("""
            SELECT stock_code, short_name, time, main_net_amount, main_behavior
            FROM monitor_gp_sssj_20260428
            WHERE main_net_amount != 0
            ORDER BY time DESC
            LIMIT 5
        """)).fetchall()
        
        if recent:
            print("\n最近更新的记录:")
            for row in recent:
                print(f"  {row[0]} {row[1]} {row[2]}: {row[3]:,.2f} ({row[4]})")

if __name__ == "__main__":
    check_progress()
