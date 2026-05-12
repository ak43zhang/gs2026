#!/usr/bin/env python3
"""测试MySQL写入功能 - 返回主键ID"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
from gs2026.utils import mysql_util, config_util, log_util

print("=" * 70)
print("MySQL写入测试")
print("=" * 70)

# 初始化MySQL工具
url = config_util.get_config('common.url')
mysql_tool = mysql_util.get_mysql_tool(url)

# 读取测试结果
with open(r'F:\pyworkspace2026\gs2026\stepfun_result_30.json', 'r', encoding='utf-8') as f:
    json_data = f.read()

print(f"\nJSON数据长度: {len(json_data)} 字符")

# 解析JSON获取第一条消息
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
print(f"  JSON长度: {len(json_data)} 字符")

# 检查表是否存在
print(f"\n检查表 analysis_area2026 是否存在...")
try:
    result = mysql_tool.update_data("SELECT 1 FROM analysis_area2026 LIMIT 1")
    print("  [OK] 表存在")
except Exception as e:
    print(f"  [FAIL] 表检查失败: {e}")
    sys.exit(1)

# 执行插入
print(f"\n执行INSERT...")
try:
    # 使用与DeepSeek版本相同的SQL格式
    sql = f"INSERT INTO analysis_area2026 (news_date, main_area, child_area, json_data) VALUES ('{t_date}', '{main_area}', '{child_area}', '{json_data.replace(chr(39), chr(39)+chr(39))}')"
    
    result = mysql_tool.update_data(sql)
    print(f"  [OK] 插入成功")
    print(f"  返回结果: {result}")
    
    # 查询最后插入的ID
    id_result = mysql_tool.query_data("SELECT LAST_INSERT_ID() as id")
    if id_result:
        last_id = id_result[0].get('id', 'N/A')
        print(f"\n  [主键ID]: {last_id}")
    
    # 验证数据
    print(f"\n验证写入数据...")
    verify_sql = f"SELECT id, news_date, main_area, child_area, LENGTH(json_data) as json_len FROM analysis_area2026 WHERE news_date='{t_date}' AND main_area='{main_area}' AND child_area='{child_area}' ORDER BY id DESC LIMIT 1"
    verify_result = mysql_tool.query_data(verify_sql)
    
    if verify_result:
        row = verify_result[0]
        print(f"  [OK] 数据验证成功")
        print(f"  记录ID: {row.get('id')}")
        print(f"  日期: {row.get('news_date')}")
        print(f"  主领域: {row.get('main_area')}")
        print(f"  子领域: {row.get('child_area')}")
        print(f"  JSON长度: {row.get('json_len')} 字节")
    else:
        print(f"  [FAIL] 未找到记录")
        
except Exception as e:
    print(f"  [FAIL] 插入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
