# -*- coding: utf-8 -*-
"""
最终验证报告 - 量化选债收益计算
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

print('='*80)
print('量化选债收益计算 - 最终验证报告')
print(f'日期: {today}')
print('='*80)

with engine.connect() as conn:
    # 1. 基础统计
    result = conn.execute(text('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_locked = 1 THEN 1 ELSE 0 END) as settled,
            SUM(CASE WHEN is_locked = 0 THEN 1 ELSE 0 END) as holding
        FROM quant_screen_hits 
        WHERE trade_date = :date
    '''), {'date': today})
    row = result.fetchone()
    
    print(f'\n【基础统计】')
    print(f'  总记录: {row.total}')
    print(f'  已结算: {row.settled}')
    print(f'  持仓中: {row.holding}')
    
    # 2. 按lock_reason统计
    result = conn.execute(text('''
        SELECT lock_reason, COUNT(*) as cnt,
               SUM(CASE WHEN final_return_pct >= 0 THEN 1 ELSE 0 END) as win,
               SUM(CASE WHEN final_return_pct < 0 THEN 1 ELSE 0 END) as loss
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 1
        GROUP BY lock_reason
    '''), {'date': today})
    
    print(f'\n【按原因统计】')
    take_profit = 0
    stop_loss = 0
    timeout_total = 0
    timeout_win = 0
    timeout_loss = 0
    
    for row in result:
        reason = row.lock_reason
        cnt = row.cnt
        win = row.win or 0
        loss = row.loss or 0
        
        if reason == 'take_profit':
            take_profit = cnt
            print(f'  止盈(take_profit): {cnt}条')
        elif reason == 'stop_loss':
            stop_loss = cnt
            print(f'  止损(stop_loss): {cnt}条')
        elif reason == 'max_time':
            timeout_total = cnt
            timeout_win = win
            timeout_loss = loss
            print(f'  超时(max_time): {cnt}条 (盈{win}条/损{loss}条)')
    
    # 3. 盈/损统计（按用户要求）
    print(f'\n【盈/损统计（按用户要求）】')
    print(f'  盈数 = 止盈({take_profit}) + 超时盈({timeout_win}) = {take_profit + timeout_win}条')
    print(f'  损数 = 止损({stop_loss}) + 超时损({timeout_loss}) = {stop_loss + timeout_loss}条')
    
    # 4. 检查final_return_pct为null的情况
    result = conn.execute(text('''
        SELECT COUNT(*) 
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 1 AND final_return_pct IS NULL
    '''), {'date': today})
    null_count = result.fetchone()[0]
    
    print(f'\n【数据完整性】')
    print(f'  final_return_pct为null的记录: {null_count}条')
    if null_count == 0:
        print(f'  ✓ 所有已结算记录都有收益值')
    else:
        print(f'  ✗ 有{null_count}条记录缺少收益值')
    
    # 5. 展示所有记录
    print(f'\n【完整记录列表】')
    print('-'*80)
    result = conn.execute(text('''
        SELECT id, bond_code, bond_name, tick_time, 
               is_locked, signal_status, lock_reason, final_return_pct,
               entry_price, exit_price
        FROM quant_screen_hits 
        WHERE trade_date = :date
        ORDER BY id DESC
    '''), {'date': today})
    
    for row in result:
        status_icon = '🔒' if row.is_locked else '📊'
        profit_str = f'{row.final_return_pct:.2f}%' if row.final_return_pct is not None else '--'
        
        # 判断是盈是损
        if row.is_locked:
            if row.lock_reason == 'take_profit':
                pnl = '盈(止盈)'
            elif row.lock_reason == 'stop_loss':
                pnl = '损(止损)'
            elif row.lock_reason == 'max_time':
                pnl = '盈(超时)' if row.final_return_pct >= 0 else '损(超时)'
            else:
                pnl = '--'
        else:
            pnl = '持仓中'
        
        print(f'{status_icon} ID:{row.id} {row.bond_code} {row.bond_name or ""}')
        print(f'   入场:{row.tick_time} 状态:{row.signal_status} 原因:{row.lock_reason}')
        print(f'   收益:{profit_str} 分类:{pnl}')
        print(f'   入场价:{row.entry_price} 出场价:{row.exit_price}')
        print()

print('='*80)
print('验证完成')
print('='*80)
