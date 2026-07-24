# -*- coding: utf-8 -*-
"""
检查持仓中记录的详细情况
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

with engine.connect() as conn:
    # 查询持仓中记录
    result = conn.execute(text('''
        SELECT id, bond_code, bond_name, tick_time, entry_price, 
               take_profit_price, stop_loss_price, max_hold_time,
               signal_status, exit_price, exit_time, hold_seconds, is_locked
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 0
    '''), {'date': today})
    
    row = result.fetchone()
    if row:
        print(f'持仓中记录详情:')
        print(f'  ID: {row.id}')
        print(f'  债券: {row.bond_code} {row.bond_name}')
        print(f'  入场时间: {row.tick_time}')
        print(f'  入场价: {row.entry_price}')
        print(f'  止盈价: {row.take_profit_price}')
        print(f'  止损价: {row.stop_loss_price}')
        print(f'  最大持仓: {row.max_hold_time}分钟')
        print(f'  当前状态: {row.signal_status}')
        print(f'  is_locked: {row.is_locked}')
        
        # 计算应该超时的时间
        from datetime import datetime, timedelta
        entry_time_str = str(row.tick_time)
        entry_hour = int(entry_time_str[0:2])
        entry_min = int(entry_time_str[2:4])
        entry_sec = int(entry_time_str[4:6])
        
        entry_dt = datetime(2026, 7, 23, entry_hour, entry_min, entry_sec)
        timeout_dt = entry_dt + timedelta(minutes=row.max_hold_time)
        
        print(f'\n超时计算:')
        print(f'  入场时间: {entry_dt.strftime("%H:%M:%S")}')
        print(f'  应超时: {timeout_dt.strftime("%H:%M:%S")}')
        print(f'  当前时间: 21:01:00')
        print(f'  是否应超时: {timeout_dt < datetime(2026, 7, 23, 21, 1, 0)}')
        
        # 检查是否有exit_price和exit_time
        print(f'\n数据库字段:')
        print(f'  exit_price: {row.exit_price}')
        print(f'  exit_time: {row.exit_time}')
        print(f'  hold_seconds: {row.hold_seconds}')
        
        # 发现问题：这条记录已经有exit_price和exit_time，但is_locked=0
        if row.exit_price and row.exit_time and not row.is_locked:
            print(f'\n⚠️ 问题发现: 记录已有exit_price和exit_time，但is_locked=0')
            print(f'  这可能是旧逻辑写入的数据，新逻辑没有正确识别')
            
            # 手动修复
            print(f'\n修复中...')
            conn.execute(text('''
                UPDATE quant_screen_hits 
                SET is_locked = 1, 
                    locked_at = NOW(),
                    lock_reason = 'max_time',
                    signal_status = 'timeout',
                    updated_at = NOW()
                WHERE id = :id
            '''), {'id': row.id})
            conn.commit()
            print(f'  已修复: ID={row.id} 设置为已锁定(timeout)')
    else:
        print('没有持仓中记录')
        
    # 再次检查
    result = conn.execute(text('''
        SELECT COUNT(*) FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 0
    '''), {'date': today})
    count = result.fetchone()[0]
    print(f'\n修复后持仓中记录数: {count}')
