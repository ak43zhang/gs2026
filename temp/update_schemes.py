#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()

with ds.engine.connect() as conn:
    # 停用强势反弹和高成交额
    conn.execute(text("""
        UPDATE quant_screen_schemes 
        SET is_active = 0 
        WHERE scheme_name IN ('强势反弹', '高成交额')
    """))
    
    # 确保大盘债券斜率共振在用
    conn.execute(text("""
        UPDATE quant_screen_schemes 
        SET is_active = 1 
        WHERE scheme_name = '大盘债券斜率共振'
    """))
    
    conn.commit()
    
    # 验证
    result = conn.execute(text('SELECT scheme_name, is_active FROM quant_screen_schemes'))
    print("=== 方案状态 ===")
    for row in result:
        status = "在用" if row.is_active else "停用"
        print(f"方案: {row.scheme_name}, 状态: {status}")
