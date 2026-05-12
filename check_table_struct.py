#!/usr/bin/env python3
"""检查表结构"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import mysql.connector

print("=" * 70)
print("检查表结构")
print("=" * 70)

try:
    conn = mysql.connector.connect(
        host="192.168.0.101",
        port=3306,
        user="root",
        password="123456",
        database="gs",
        charset="utf8"
    )
    cursor = conn.cursor()
    
    # 检查analysis_area2026表结构
    print("\nanalysis_area2026 表结构:")
    cursor.execute("DESCRIBE analysis_area2026")
    for row in cursor.fetchall():
        print(f"  {row}")
    
    # 检查analysis_area2025表结构（参考）
    print("\nanalysis_area2025 表结构:")
    try:
        cursor.execute("DESCRIBE analysis_area2025")
        for row in cursor.fetchall():
            print(f"  {row}")
    except:
        print("  表不存在")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"失败: {e}")
