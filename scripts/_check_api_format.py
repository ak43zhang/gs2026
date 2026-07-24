# -*- coding: utf-8 -*-
"""
检查API返回的数据格式
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

with engine.connect() as conn:
    # 模拟API查询
    result = conn.execute(text('''
        SELECT id, bond_code, bond_name, tick_time, entry_price, 
               take_profit_price, stop_loss_price, max_hold_time,
               is_locked, signal_status, lock_reason, 
               final_return_pct, exit_price, exit_time, hold_seconds
        FROM quant_screen_hits 
        WHERE trade_date = :date
        ORDER BY id DESC
        LIMIT 5
    '''), {'date': today})
    
    print('API返回数据格式检查:')
    print('='*80)
    
    for row in result:
        hit = {
            'id': row.id,
            'bond_code': row.bond_code,
            'bond_name': row.bond_name,
            'tick_time': str(row.tick_time),
            'entry_price': float(row.entry_price) if row.entry_price else None,
            'take_profit_price': float(row.take_profit_price) if row.take_profit_price else None,
            'stop_loss_price': float(row.stop_loss_price) if row.stop_loss_price else None,
            'max_hold_time': row.max_hold_time,
            'is_locked': bool(row.is_locked),
            'signal_status': row.signal_status,
            'lock_reason': row.lock_reason,
            'final_return_pct': float(row.final_return_pct) if row.final_return_pct is not None else None,
            'exit_price': float(row.exit_price) if row.exit_price else None,
            'exit_time': str(row.exit_time) if row.exit_time else None,
            'hold_seconds': row.hold_seconds
        }
        
        print(f'\nID:{hit["id"]} {hit["bond_code"]}')
        print(f'  is_locked: {hit["is_locked"]} (type: {type(hit["is_locked"]).__name__})')
        print(f'  final_return_pct: {hit["final_return_pct"]} (type: {type(hit["final_return_pct"]).__name__})')
        print(f'  lock_reason: {hit["lock_reason"]}')
        
        # 检查前端逻辑
        if hit['is_locked']:
            # 已结算
            if hit['final_return_pct'] is not None:
                display_return = f'{hit["final_return_pct"]:.4f}'
            else:
                display_return = '--'
            print(f'  前端显示: {display_return}')
        else:
            print(f'  前端显示: 持仓中（实时计算）')

print('\n' + '='*80)
print('检查完成')
