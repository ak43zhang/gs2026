#!/usr/bin/env python
"""查询 2026-05-19 09:41:33 的买点候选记录"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, connect_args={'connect_timeout': 10})

with engine.connect() as conn:
    # 查询该时间点的记录
    result = conn.execute(text("""
        SELECT stock_code, stock_name, level, star_color, market_context
        FROM buy_point_candidates 
        WHERE date = '2026-05-19' AND time = '09:41:33'
        ORDER BY level DESC
    """))
    rows = result.fetchall()
    
    if not rows:
        print("No records found for 2026-05-19 09:41:33")
    else:
        print(f"Found {len(rows)} records:\n")
        for r in rows:
            print(f"  Code: {r[0]}, Name: {r[1]}, Level: {r[2]}, StarColor: {r[3]}")
        
        # 检查 market_context 中的 criticalHit
        import json
        mkt = r[4]
        if mkt:
            try:
                mkt_data = json.loads(mkt) if isinstance(mkt, str) else mkt
                print(f"\nMarket Context:")
                print(f"  criticalHit: {mkt_data.get('criticalHit', 'NOT SET')}")
                print(f"  passed: {mkt_data.get('passed')}")
                print(f"  total: {mkt_data.get('total')}")
                print(f"  signal: {mkt_data.get('signal')}")
                conds = mkt_data.get('conditions', [])
                for c in conds:
                    print(f"  - {c.get('name')}: {'PASS' if c.get('passed') else 'FAIL'}")
            except Exception as e:
                print(f"  Parse error: {e}")

    # 检查表结构
    print("\n\nTable columns:")
    result = conn.execute(text("""
        SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'gs' AND TABLE_NAME = 'buy_point_candidates'
        ORDER BY ORDINAL_POSITION
    """))
    for r in result.fetchall():
        print(f"  {r[0]}: {r[1]} (default: {r[2]})")
