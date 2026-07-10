#!/usr/bin/env python3
"""排查量化选债不命中原因"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import pymysql

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root',
    password='123456', database='gs', charset='utf8'
)

try:
    with conn.cursor() as cursor:
        # 1. 查看在用方案条件
        cursor.execute("""
            SELECT scheme_name, conditions_json, is_active, use_realtime
            FROM quant_screen_schemes 
            WHERE is_active = 1
        """)
        rows = cursor.fetchall()
        print("=== 在用方案 ===")
        for row in rows:
            print(f"  方案: {row[0]}")
            print(f"  is_active={row[2]}, use_realtime={row[3]}")
            conditions = json.loads(row[1]) if row[1] else []
            print(f"  条件数: {len(conditions)}")
            for c in conditions:
                print(f"    {c['field']} {c['op']} {c['value']}")
            print()
        
        # 2. 查看最新tick数据的字段
        cursor.execute("""
            SELECT COLUMN_NAME FROM information_schema.columns 
            WHERE table_schema = 'gs' AND table_name = 'monitor_zq_sssj_20260710'
            ORDER BY ORDINAL_POSITION
        """)
        cols = [r[0] for r in cursor.fetchall()]
        print(f"=== 今日数据表字段 ({len(cols)}) ===")
        print(f"  {', '.join(cols)}")
        
        # 3. 查看最新一条数据的相关字段值
        cursor.execute("""
            SELECT time, bond_code, bond_name, price, change_pct, amount, 
                   slope_short, mkt_slope_short, mkt_slope_long
            FROM monitor_zq_sssj_20260710
            ORDER BY time DESC LIMIT 5
        """)
        print("\n=== 最新5条数据 ===")
        for row in cursor.fetchall():
            print(f"  time={row[0]} code={row[1]} price={row[3]} change_pct={row[4]} "
                  f"amount={row[5]} slope_short={row[6]} mkt_slope_short={row[7]} mkt_slope_long={row[8]}")
        
        # 4. 检查满足条件的数据数量（手动应用条件）
        print("\n=== 手动检查条件 ===")
        if rows:
            conditions = json.loads(rows[0][1]) if rows[0][1] else []
            where_parts = []
            for c in conditions:
                field = c['field']
                op = c['op']
                val = c['value']
                if op == 'between':
                    where_parts.append(f"{field} BETWEEN {val} AND {c.get('value2', val)}")
                else:
                    where_parts.append(f"{field} {op} {val}")
            
            if where_parts:
                where_clause = " AND ".join(where_parts)
                sql = f"SELECT COUNT(*) FROM monitor_zq_sssj_20260710 WHERE {where_clause}"
                print(f"  SQL: SELECT COUNT(*) ... WHERE {where_clause}")
                try:
                    cursor.execute(sql)
                    count = cursor.fetchone()[0]
                    print(f"  满足条件总数: {count}")
                except Exception as e:
                    print(f"  SQL执行失败: {e}")
                
                # 查最新tick满足条件的
                sql2 = f"""
                    SELECT time, bond_code, bond_name, price, change_pct 
                    FROM monitor_zq_sssj_20260710 
                    WHERE {where_clause}
                    ORDER BY time DESC LIMIT 10
                """
                try:
                    cursor.execute(sql2)
                    print(f"\n  最新满足条件的记录:")
                    for row in cursor.fetchall():
                        print(f"    time={row[0]} {row[1]} {row[2]} price={row[3]} change={row[4]}%")
                except Exception as e:
                    print(f"  SQL执行失败: {e}")
finally:
    conn.close()
