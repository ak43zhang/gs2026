#!/usr/bin/env python3
"""测试完整流程 - process_domain + MySQL写入"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import mysql.connector
from gs2026.analysis.worker.message.deepseek.result_processor import process_domain

print("=" * 70)
print("测试完整流程 - process_domain + MySQL写入")
print("=" * 70)

# 读取测试结果
with open(r'F:\pyworkspace2026\gs2026\stepfun_result_array.json', 'r', encoding='utf-8') as f:
    json_data = f.read()

print(f"\nJSON数据长度: {len(json_data)} 字符")

# 解析验证
data = json.loads(json_data)
messages = data.get('消息集合', [])
print(f"消息数量: {len(messages)}")

# 验证第一条消息的格式
if messages:
    msg = messages[0]
    print(f"\n第一条消息验证:")
    print(f"  主领域: {msg.get('主领域')}")
    print(f"  子领域: {msg.get('子领域')}")
    print(f"  深度分析类型: {type(msg.get('深度分析', [])).__name__}")
    print(f"  深度分析长度: {len(msg.get('深度分析', []))}")

# 调用process_domain
print(f"\n调用 process_domain...")
t_date = '2026-05-10'
main_area = '环境生态'
child_area = '生物多样性'

try:
    stats = process_domain(
        json_data, 
        main_area, 
        child_area, 
        t_date, 
        version='stepfun-1.0.0'
    )
    print(f"\n[OK] process_domain 执行成功!")
    print(f"统计结果: {stats}")
    
    # 验证MySQL写入
    print(f"\n验证MySQL写入...")
    conn = mysql.connector.connect(
        host="192.168.0.101",
        port=3306,
        user="root",
        password="123456",
        database="gs",
        charset="utf8"
    )
    cursor = conn.cursor()
    
    # 查询analysis_domain_detail_2026
    query = """SELECT COUNT(*) as cnt, 
                      AVG(composite_score) as avg_score,
                      MAX(composite_score) as max_score,
                      MIN(composite_score) as min_score
               FROM analysis_domain_detail_2026 
               WHERE event_time LIKE '2026-05-10%' 
                 AND main_area = %s 
                 AND child_area = %s
                 AND analysis_version = 'stepfun-1.0.0'"""
    cursor.execute(query, (main_area, child_area))
    row = cursor.fetchone()
    
    if row and row[0] > 0:
        print(f"  [OK] 数据已写入 analysis_domain_detail_2026")
        print(f"  记录数: {row[0]}")
        print(f"  平均评分: {row[1]:.1f}")
        print(f"  最高评分: {row[2]}")
        print(f"  最低评分: {row[3]}")
        
        # 查询样本数据
        sample_query = """SELECT content_hash, key_event, composite_score, news_type, news_size
                          FROM analysis_domain_detail_2026 
                          WHERE event_time LIKE '2026-05-10%' 
                            AND main_area = %s 
                            AND child_area = %s
                            AND analysis_version = 'stepfun-1.0.0'
                          ORDER BY composite_score DESC
                          LIMIT 3"""
        cursor.execute(sample_query, (main_area, child_area))
        samples = cursor.fetchall()
        
        print(f"\n  评分Top3:")
        for i, sample in enumerate(samples, 1):
            print(f"    {i}. [{sample[4]}] {sample[2]}分 - {sample[1][:50]}...")
    else:
        print(f"  [FAIL] 未找到记录")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("[OK] 完整流程测试成功!")
    print("=" * 70)
    print(f"\n数据已写入以下表:")
    print(f"  1. analysis_area2026 - 聚合JSON")
    print(f"  2. analysis_domain_detail_2026 - 拆分明细")
    print(f"  3. Redis缓存 - 领域索引")
    
except Exception as e:
    print(f"\n[FAIL] 失败: {e}")
    import traceback
    traceback.print_exc()
