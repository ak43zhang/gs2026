#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()
with ds.engine.connect() as conn:
    result = conn.execute(text('SELECT scheme_name, is_active, use_replay FROM quant_screen_schemes'))
    print("=== 方案列表 ===")
    for row in result:
        print(f"方案: {row.scheme_name}, 在用: {row.is_active}, 回放: {row.use_replay}")
    
    # 检查quant_screen_hits表
    print("\n=== 历史命中统计 ===")
    result2 = conn.execute(text('SELECT COUNT(*) as cnt FROM quant_screen_hits'))
    cnt = result2.fetchone().cnt
    print(f"总记录数: {cnt}")
    
    if cnt > 0:
        result3 = conn.execute(text('SELECT trade_date, COUNT(*) as cnt FROM quant_screen_hits GROUP BY trade_date'))
        print("\n按日期统计:")
        for row in result3:
            print(f"  {row.trade_date}: {row.cnt}条")
