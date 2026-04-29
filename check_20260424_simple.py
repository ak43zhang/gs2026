#!/usr/bin/env python3
"""
简单检查2026-04-24数据
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("2026-04-24 数据检查")
print("=" * 80)

with engine.connect() as conn:
    # 1. 检查表是否存在
    print("\n【1. 检查表是否存在】")
    try:
        result = conn.execute(text("SHOW TABLES LIKE 'monitor_gp_sssj_20260424'"))
        tables = result.fetchall()
        if tables:
            print(f"  表 monitor_gp_sssj_20260424 存在")
        else:
            print(f"  表 monitor_gp_sssj_20260424 不存在！")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 2. 检查记录数
    print("\n【2. 检查记录数】")
    try:
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260424"))
        count = result.scalar()
        print(f"  记录数: {count}")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 3. 检查字段
    print("\n【3. 检查字段】")
    try:
        result = conn.execute(text("DESCRIBE monitor_gp_sssj_20260424"))
        columns = result.fetchall()
        print(f"  字段数: {len(columns)}")
        for col in columns:
            print(f"    {col[0]}: {col[1]}")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 4. 检查change_pct字段
    print("\n【4. 检查change_pct字段】")
    try:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) as null_count,
                SUM(CASE WHEN change_pct = 0 THEN 1 ELSE 0 END) as zero_count
            FROM monitor_gp_sssj_20260424
        """))
        row = result.fetchone()
        print(f"  总记录: {row[0]}")
        print(f"  NULL值: {row[1]}")
        print(f"  零值: {row[2]}")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 5. 检查main_net_amount字段
    print("\n【5. 检查main_net_amount字段】")
    try:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount IS NULL THEN 1 ELSE 0 END) as null_count,
                SUM(CASE WHEN main_net_amount = 0 THEN 1 ELSE 0 END) as zero_count
            FROM monitor_gp_sssj_20260424
        """))
        row = result.fetchone()
        print(f"  总记录: {row[0]}")
        print(f"  NULL值: {row[1]}")
        print(f"  零值: {row[2]}")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 6. 对比2026-04-28
    print("\n【6. 对比2026-04-28】")
    try:
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260428"))
        count_28 = result.scalar()
        print(f"  2026-04-28记录数: {count_28}")
        
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260424"))
        count_24 = result.scalar()
        print(f"  2026-04-24记录数: {count_24}")
    except Exception as e:
        print(f"  错误: {e}")

print("\n" + "=" * 80)
print("检查完成")
