#!/usr/bin/env python3
"""测试MySQL写入功能 - 简化版"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import mysql.connector
from gs2026.utils import config_util

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
    
    # 执行插入
    print(f"\n执行INSERT...")
    sql = """INSERT INTO analysis_area2026 (news_date, main_area, child_area, json_data) VALUES (%s, %s, %s, %s)"""
    cursor.execute(sql, (t_date, main_area, child_area, json_data))
    conn.commit()
    
    last_id = cursor.lastrowid
    print(f"  [OK] 插入成功")
    print(f"  [主键ID]: {last_id}")
    
    # 验证数据
    print(f"\n验证写入数据...")
    verify_sql = "SELECT id, news_date, main_area, child_area, LENGTH(json_data) as json_len FROM analysis_area2026 WHERE id = %s"
    cursor.execute(verify_sql, (last_id,))
    row = cursor.fetchone()
    
    if row:
        print(f"  [OK] 数据验证成功")
        print(f"  记录ID: {row[0]}")
        print(f"  日期: {row[1]}")
        print(f"  主领域: {row[2]}")
        print(f"  子领域: {row[3]}")
        print(f"  JSON长度: {row[4]} 字节")
        
        # 返回主键ID
        print(f"\n" + "=" * 70)
        print(f"主键ID: {row[0]}")
        print(f"前端查询SQL: SELECT * FROM analysis_area2026 WHERE id = {row[0]}")
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
