#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()

with ds.engine.connect() as conn:
    # 检查quant_screen_hits表
    print("=== 历史命中统计 ===")
    result = conn.execute(text('SELECT COUNT(*) as cnt FROM quant_screen_hits'))
    cnt = result.fetchone().cnt
    print(f"总记录数: {cnt}")
    
    if cnt > 0:
        result2 = conn.execute(text('SELECT trade_date, COUNT(*) as cnt FROM quant_screen_hits GROUP BY trade_date'))
        print("\n按日期统计:")
        for row in result2:
            print(f"  {row.trade_date}: {row.cnt}条")
        
        # 查看最新记录
        result3 = conn.execute(text('SELECT * FROM quant_screen_hits ORDER BY id DESC LIMIT 5'))
        print("\n最新5条记录:")
        for row in result3:
            print(f"  {row.id} | {row.trade_date} | {row.tick_time} | {row.scheme_name} | {row.bond_code}")
    else:
        print("\n暂无命中记录")
