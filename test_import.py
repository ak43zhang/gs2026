#!/usr/bin/env python3
"""检查data_service导入是否会导致循环导入"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

print("测试导入data_service...")
try:
    from gs2026.dashboard.services.data_service import DataService
    print("[OK] DataService导入成功")
    
    ds = DataService()
    print("[OK] DataService实例化成功")
    
    # 测试get_stock_ranking
    print("\n测试get_stock_ranking...")
    result = ds.get_stock_ranking(limit=2, date='20260427', use_mysql=True)
    print(f"[OK] 返回 {len(result)} 条数据")
    
    if result:
        print(f"第一条数据字段: {list(result[0].keys())}")
        print(f"bond_code: {result[0].get('bond_code', 'N/A')}")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
