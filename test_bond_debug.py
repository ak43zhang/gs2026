#!/usr/bin/env python3
"""调试债券排行问题"""

import sys
sys.path.insert(0, 'src')

from gs2026.utils import mysql_util, redis_util
import pandas as pd

# 初始化
redis_util.init_redis(host='localhost', port=6379, decode_responses=False)
mysql_tool = mysql_util.MysqlTool()
engine = mysql_tool.engine

print("=== 调试债券排行问题 ===\n")

# 1. 检查Redis中的债券数据
print("1. 检查Redis中的债券数据:")
client = redis_util._get_redis_client()
keys = client.keys('monitor_zq_sssj_*')
print(f"   找到 {len(keys)} 个债券sssj key")

if keys:
    # 按日期分组
    from collections import defaultdict
    date_keys = defaultdict(list)
    for key in keys:
        key_str = key.decode() if isinstance(key, bytes) else key
        parts = key_str.split('_')
        if len(parts) >= 3:
            date = parts[-1].split(':')[0]
            date_keys[date].append(key_str)
    
    print("   按日期分布:")
    for date in sorted(date_keys.keys()):
        print(f"     {date}: {len(date_keys[date])} keys")
        if date_keys[date]:
            print(f"       样例: {date_keys[date][0]}")

# 2. 检查MySQL中的债券数据
print("\n2. 检查MySQL中的债券数据:")
try:
    df = pd.read_sql("SHOW TABLES LIKE 'monitor_zq_sssj_%'", engine)
    tables = df.iloc[:, 0].tolist()
    print(f"   找到 {len(tables)} 个债券sssj表")
    for table in tables[:3]:
        print(f"     - {table}")
except Exception as e:
    print(f"   错误: {e}")

# 3. 测试获取债券数据
print("\n3. 测试获取债券数据 (20260401):")
try:
    # 从Redis获取
    redis_key = "monitor_zq_sssj_20260401:09:30:00"
    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    if df is not None and not df.empty:
        print(f"   Redis命中: {redis_key}")
        print(f"   数据行数: {len(df)}")
        print(f"   列名: {df.columns.tolist()}")
    else:
        print(f"   Redis未命中: {redis_key}")
        
        # 从MySQL获取
        try:
            df = pd.read_sql("SELECT * FROM monitor_zq_sssj_20260401 WHERE time = '09:30:00' LIMIT 3", engine)
            print(f"   MySQL查询结果:")
            print(f"   数据行数: {len(df)}")
            if not df.empty:
                print(f"   列名: {df.columns.tolist()}")
        except Exception as e:
            print(f"   MySQL错误: {e}")
except Exception as e:
    print(f"   错误: {e}")

# 4. 测试债券排行API
print("\n4. 测试债券排行增强功能:")
try:
    from gs2026.dashboard2.routes.monitor import _get_bond_change_pct_batch, _enrich_bond_data
    
    # 模拟债券数据
    test_bonds = [
        {'code': '123001', 'name': '测试债券1'},
        {'code': '123002', 'name': '测试债券2'},
    ]
    
    # 测试获取涨跌幅
    result = _get_bond_change_pct_batch('20260401', '09:30:00', ['123001', '123002'])
    print(f"   涨跌幅查询结果: {result}")
    
except Exception as e:
    print(f"   错误: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 调试完成 ===")
