#!/usr/bin/env python3
"""检查主力净额填充进度"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy import create_engine, text

DB_CONFIG = {
    'host': '192.168.0.101',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gs'
}

def get_engine():
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    return create_engine(url)

engine = get_engine()

with engine.connect() as conn:
    # 检查总记录数
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as has_main_force
        FROM monitor_gp_sssj_20260428
    """)).fetchone()
    
    total = result[0]
    has_main = result[1]
    
    print(f"总记录数: {total:,}")
    print(f"已填充主力净额: {has_main:,} ({has_main/total*100:.1f}%)")
    
    # 检查最近更新的时间
    result2 = conn.execute(text("""
        SELECT MAX(time) as latest_time
        FROM monitor_gp_sssj_20260428
        WHERE main_net_amount != 0
    """)).fetchone()
    
    if result2[0]:
        print(f"最新填充时间: {result2[0]}")
    
    # 查看某只股票的样本数据
    result3 = conn.execute(text("""
        SELECT time, price, main_net_amount, main_behavior
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000539'
        AND main_net_amount != 0
        ORDER BY time
        LIMIT 5
    """)).fetchall()
    
    print("\n000539 样本数据:")
    for row in result3:
        print(f"  {row[0]}: 价格={row[1]:.2f}, 净额={row[2]:,.0f}, 行为={row[3]}")
