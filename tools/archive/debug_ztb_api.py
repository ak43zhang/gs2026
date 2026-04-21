#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""排查涨停分析API问题"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_list, get_ztb_detail
from gs2026.utils import log_util

logger = log_util.setup_logger(__name__)

print("=" * 60)
print("涨停分析API排查")
print("=" * 60)

# 测试列表查询
print("\n【测试1】列表查询")
print("-" * 40)
try:
    result = get_ztb_list(date='20260413', page=1, page_size=5)
    print(f"返回数据条数: {len(result.get('items', []))}")
    print(f"总数: {result.get('total', 0)}")
    print(f"页码: {result.get('page', 0)}")
    if result.get('items'):
        print(f"\n第一条数据:")
        item = result['items'][0]
        print(f"  - 股票: {item.get('stock_name')} ({item.get('stock_code')})")
        print(f"  - 涨停时间: {item.get('zt_time')}")
        print(f"  - 时段: {item.get('zt_time_range')}")
    else:
        print("  警告: 返回空列表")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

# 测试详情查询
print("\n【测试2】详情查询")
print("-" * 40)
try:
    # 先获取一个content_hash
    result = get_ztb_list(date='20260413', page=1, page_size=1)
    if result.get('items'):
        content_hash = result['items'][0].get('content_hash')
        print(f"查询content_hash: {content_hash}")
        
        detail = get_ztb_detail(content_hash, date='20260413')
        if detail:
            print(f"详情返回: 成功")
            print(f"  - 股票: {detail.get('stock_name')}")
            print(f"  - sector_msg类型: {type(detail.get('sector_msg'))}")
            print(f"  - concept_msg类型: {type(detail.get('concept_msg'))}")
        else:
            print("详情返回: None")
    else:
        print("无法获取content_hash进行测试")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

# 测试数据库连接
print("\n【测试3】数据库连接")
print("-" * 40)
try:
    from gs2026.dashboard2.services.ztb_analysis_service import engine
    import pandas as pd
    
    sql = "SELECT COUNT(*) as total FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-13'"
    df = pd.read_sql(sql, engine)
    print(f"数据库记录数: {df.iloc[0]['total']}")
except Exception as e:
    print(f"错误: {e}")

print("\n" + "=" * 60)
print("排查完成")
print("=" * 60)
