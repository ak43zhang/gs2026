# -*- coding: utf-8 -*-
"""
修复ID:197473的final_return_pct
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)

with engine.connect() as conn:
    # 获取该记录的详细信息
    result = conn.execute(text('''
        SELECT entry_price, exit_price
        FROM quant_screen_hits 
        WHERE id = 197473
    '''))
    row = result.fetchone()
    
    if row:
        entry = float(row.entry_price)
        exit_p = float(row.exit_price)
        profit_pct = round((exit_p - entry) / entry * 100, 4)
        
        print(f'计算收益:')
        print(f'  入场价: {entry}')
        print(f'  出场价: {exit_p}')
        print(f'  收益: {profit_pct}%')
        
        # 更新final_return_pct
        conn.execute(text('''
            UPDATE quant_screen_hits 
            SET final_return_pct = :profit
            WHERE id = 197473
        '''), {'profit': profit_pct})
        conn.commit()
        
        print(f'  已更新ID:197473的final_return_pct = {profit_pct}%')
    
    # 验证
    result = conn.execute(text('''
        SELECT id, bond_code, lock_reason, final_return_pct
        FROM quant_screen_hits 
        WHERE id = 197473
    '''))
    row = result.fetchone()
    print(f'\n验证: ID:{row.id} {row.bond_code} reason={row.lock_reason} profit={row.final_return_pct}')
