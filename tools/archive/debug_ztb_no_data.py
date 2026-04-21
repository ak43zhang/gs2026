#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""排查涨停分析数据加载问题"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 测试数据库连接和查询
from sqlalchemy import create_engine
import json

url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs"
engine = create_engine(url)

print("=" * 60)
print("涨停分析数据排查")
print("=" * 60)

# 1. 检查表是否存在
print("\n【1】检查表是否存在")
print("-" * 40)
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SHOW TABLES LIKE 'analysis_ztb_detail_2026'"))
        tables = result.fetchall()
        if tables:
            print(f"✅ 表存在: {tables[0][0]}")
        else:
            print("❌ 表不存在")
except Exception as e:
    print(f"❌ 错误: {e}")

# 2. 检查数据量
print("\n【2】检查数据量")
print("-" * 40)
try:
    import pandas as pd
    sql = "SELECT COUNT(*) as total FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-13'"
    df = pd.read_sql(sql, engine)
    print(f"2026-04-13 数据量: {df.iloc[0]['total']}")
    
    sql = "SELECT COUNT(*) as total FROM analysis_ztb_detail_2026"
    df = pd.read_sql(sql, engine)
    print(f"总数据量: {df.iloc[0]['total']}")
except Exception as e:
    print(f"❌ 错误: {e}")

# 3. 检查服务层查询
print("\n【3】测试服务层查询")
print("-" * 40)
try:
    from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_list
    result = get_ztb_list(date='20260413', page=1, page_size=5)
    print(f"返回数据条数: {len(result.get('items', []))}")
    print(f"总数: {result.get('total', 0)}")
    if result.get('items'):
        print(f"第一条: {result['items'][0].get('stock_name')} ({result['items'][0].get('stock_code')})")
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 4. 检查Flask路由
print("\n【4】检查Flask蓝图注册")
print("-" * 40)
try:
    from gs2026.dashboard2.app import create_app
    app = create_app()
    
    # 列出所有路由
    print("已注册的路由:")
    for rule in app.url_map.iter_rules():
        if 'ztb' in rule.endpoint or 'analysis' in rule.endpoint:
            print(f"  {rule.endpoint}: {rule.rule}")
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

# 5. 测试API响应
print("\n【5】测试Flask客户端请求")
print("-" * 40)
try:
    with app.test_client() as client:
        resp = client.get('/api/ztb/list?date=20260413&page=1&page_size=5')
        print(f"状态码: {resp.status_code}")
        data = resp.get_json()
        print(f"返回code: {data.get('code')}")
        print(f"返回message: {data.get('message')}")
        print(f"数据条数: {len(data.get('data', {}).get('items', []))}")
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("排查完成")
print("=" * 60)
