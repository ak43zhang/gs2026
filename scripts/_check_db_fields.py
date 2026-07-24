# -*- coding: utf-8 -*-
"""
检查数据库中final_return_pct和lock_reason字段
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

with engine.connect() as conn:
    # 查询所有已结算记录
    result = conn.execute(text('''
        SELECT id, bond_code, signal_status, lock_reason, 
               final_return_pct, exit_price, is_locked
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 1
        ORDER BY lock_reason, final_return_pct
    '''), {'date': today})
    
    rows = result.fetchall()
    
    print('已结算记录详情:')
    print('-' * 80)
    
    # 分类统计
    take_profit = []
    stop_loss = []
    timeout_profit = []  # 超时且>=0
    timeout_loss = []   # 超时且<0
    
    for row in rows:
        profit = row.final_return_pct
        reason = row.lock_reason
        
        print(f'ID:{row.id} {row.bond_code} status={row.signal_status} reason={reason} profit={profit}')
        
        if reason == 'take_profit':
            take_profit.append(row)
        elif reason == 'stop_loss':
            stop_loss.append(row)
        elif reason == 'max_time':
            if profit is not None and profit >= 0:
                timeout_profit.append(row)
            else:
                timeout_loss.append(row)
    
    print()
    print('统计验证:')
    print(f'  止盈(take_profit): {len(take_profit)} 条')
    print(f'  止损(stop_loss): {len(stop_loss)} 条')
    print(f'  超时盈(max_time >=0): {len(timeout_profit)} 条')
    print(f'  超时损(max_time <0): {len(timeout_loss)} 条')
    print()
    print(f'  盈总计(止盈+超时盈): {len(take_profit) + len(timeout_profit)} 条')
    print(f'  损总计(止损+超时损): {len(stop_loss) + len(timeout_loss)} 条')
    
    # 检查final_return_pct为null的记录
    print()
    print('检查final_return_pct为null的记录:')
    result = conn.execute(text('''
        SELECT id, bond_code, lock_reason, final_return_pct
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 1 AND final_return_pct IS NULL
    '''), {'date': today})
    null_rows = result.fetchall()
    if null_rows:
        for row in null_rows:
            print(f'  ID:{row.id} {row.bond_code} reason={row.lock_reason} profit=NULL')
    else:
        print('  无')
