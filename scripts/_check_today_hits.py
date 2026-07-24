# -*- coding: utf-8 -*-
"""
检查今日量化选债命中记录状态
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)

today = '20260723'

with engine.connect() as conn:
    # 查询今日命中记录统计
    result = conn.execute(text('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_locked = 1 THEN 1 ELSE 0 END) as settled,
            SUM(CASE WHEN is_locked = 0 THEN 1 ELSE 0 END) as holding,
            SUM(CASE WHEN signal_status = 'profited' THEN 1 ELSE 0 END) as profited,
            SUM(CASE WHEN signal_status = 'stopped' THEN 1 ELSE 0 END) as stopped,
            SUM(CASE WHEN signal_status = 'timeout' THEN 1 ELSE 0 END) as timeout
        FROM quant_screen_hits 
        WHERE trade_date = :date
    '''), {'date': today})
    row = result.fetchone()
    print(f'今日统计:')
    print(f'  总记录: {row.total}')
    print(f'  已结算: {row.settled}')
    print(f'  持仓中: {row.holding}')
    print(f'  止盈: {row.profited}')
    print(f'  止损: {row.stopped}')
    print(f'  超时: {row.timeout}')
    
    # 查询几条样本
    print(f'\n最新5条记录:')
    result = conn.execute(text('''
        SELECT id, bond_code, tick_time, entry_price, take_profit_price, stop_loss_price,
               is_locked, signal_status, lock_reason, final_return_pct, exit_price
        FROM quant_screen_hits 
        WHERE trade_date = :date
        ORDER BY id DESC
        LIMIT 5
    '''), {'date': today})
    for row in result:
        status = row.signal_status or 'entry'
        locked = '已锁定' if row.is_locked else '持仓中'
        profit = f'{row.final_return_pct:.2f}%' if row.final_return_pct is not None else 'N/A'
        print(f'  ID:{row.id} {row.bond_code} {locked} status={status} profit={profit}')
