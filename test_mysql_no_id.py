#!/usr/bin/env python3
"""测试MySQL写入功能 - 无ID版本"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import mysql.connector
from datetime import datetime

print("=" * 70)
print("MySQL写入测试")
print("=" * 70)

# 读取测试结果
with open(r'F:\pyworkspace2026\gs2026\stepfun_result_30.json', 'r', encoding='utf-8') as f:
    json_data = f.read()

print(f"\nJSON数据长度: {len(json_data)} 字符")

# 解析JSON
data = json.loads(json_data)
messages = data.get('消息集合', [])
first_msg = messages[0] if messages else {}

# 测试数据
t_date = '2026-05-10'
main_area = first_msg.get('主领域', '环境生态')
child_area = first_msg.get('子领域', '生物多样性')

print(f"\n准备写入数据:")
print(f"  日期: {t_date}")
print(f"  主领域: {main_area}")
print(f"  子领域: {child_area}")

# 连接数据库
print(f"\n连接数据库...")
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
    print("  [OK] 连接成功")
    
    # 先查询现有记录数
    print(f"\n查询现有记录...")
    count_sql = "SELECT COUNT(*) FROM analysis_area2026 WHERE news_date = %s AND main_area = %s AND child_area = %s"
    cursor.execute(count_sql, (t_date, main_area, child_area))
    before_count = cursor.fetchone()[0]
    print(f"  插入前记录数: {before_count}")
    
    # 执行插入
    print(f"\n执行INSERT...")
    sql = """INSERT INTO analysis_area2026 (news_date, main_area, child_area, json_data) VALUES (%s, %s, %s, %s)"""
    cursor.execute(sql, (t_date, main_area, child_area, json_data))
    conn.commit()
    
    print(f"  [OK] 插入成功")
    
    # 查询插入后的记录数
    cursor.execute(count_sql, (t_date, main_area, child_area))
    after_count = cursor.fetchone()[0]
    print(f"  插入后记录数: {after_count}")
    
    # 验证数据
    print(f"\n验证写入数据...")
    verify_sql = """SELECT news_date, main_area, child_area, LENGTH(json_data) as json_len, LEFT(json_data, 100) as json_preview 
                    FROM analysis_area2026 
                    WHERE news_date = %s AND main_area = %s AND child_area = %s 
                    ORDER BY json_len DESC LIMIT 1"""
    cursor.execute(verify_sql, (t_date, main_area, child_area))
    row = cursor.fetchone()
    
    if row:
        print(f"  [OK] 数据验证成功")
        print(f"  日期: {row[0]}")
        print(f"  主领域: {row[1]}")
        print(f"  子领域: {row[2]}")
        print(f"  JSON长度: {row[3]} 字节")
        print(f"  JSON预览: {row[4]}...")
        
        # 返回查询条件
        print(f"\n" + "=" * 70)
        print(f"写入成功！")
        print(f"查询条件:")
        print(f"  news_date = '{t_date}'")
        print(f"  main_area = '{main_area}'")
        print(f"  child_area = '{child_area}'")
        print(f"\n前端查询SQL:")
        print(f"  SELECT * FROM analysis_area2026")
        print(f"  WHERE news_date = '{t_date}'")
        print(f"    AND main_area = '{main_area}'")
        print(f"    AND child_area = '{child_area}'")
        print("=" * 70)
    else:
        print(f"  [FAIL] 未找到记录")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"  [FAIL] 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试完成")
