# -*- coding: utf-8 -*-
"""
生成今日命中记录详细报告，供前端验证
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

with engine.connect() as conn:
    # 查询所有记录
    result = conn.execute(text('''
        SELECT id, bond_code, bond_name, tick_time, entry_price, 
               take_profit_price, stop_loss_price, max_hold_time,
               is_locked, signal_status, lock_reason, 
               final_return_pct, exit_price, exit_time, hold_seconds
        FROM quant_screen_hits 
        WHERE trade_date = :date
        ORDER BY id DESC
    '''), {'date': today})
    
    rows = result.fetchall()
    
    print(f'今日命中记录详细报告 ({today})')
    print('='*80)
    print(f'总记录数: {len(rows)}')
    print()
    
    # 分类统计
    settled = [r for r in rows if r.is_locked]
    holding = [r for r in rows if not r.is_locked]
    profited = [r for r in rows if r.signal_status == 'profited']
    stopped = [r for r in rows if r.signal_status == 'stopped']
    timeout = [r for r in rows if r.signal_status == 'timeout']
    
    print(f'【统计概览】')
    print(f'  已结算: {len(settled)} 条')
    print(f'  持仓中: {len(holding)} 条')
    print(f'  止盈: {len(profited)} 条')
    print(f'  止损: {len(stopped)} 条')
    print(f'  超时: {len(timeout)} 条')
    print()
    
    # 计算盈亏统计
    if settled:
        profits = [r.final_return_pct for r in settled if r.final_return_pct is not None]
        if profits:
            avg_profit = sum(profits) / len(profits)
            total_profit = sum(profits)
            win_count = sum(1 for p in profits if p >= 0)
            loss_count = sum(1 for p in profits if p < 0)
            print(f'【盈亏统计】')
            print(f'  平均收益: {avg_profit:.2f}%')
            print(f'  总收益: {total_profit:.2f}%')
            print(f'  盈利次数: {win_count} ({win_count/len(profits)*100:.1f}%)')
            print(f'  亏损次数: {loss_count} ({loss_count/len(profits)*100:.1f}%)')
            print()
    
    # 详细记录
    print(f'【详细记录】')
    print('-'*80)
    
    for row in rows:
        status_icon = '🔒' if row.is_locked else '📊'
        status_text = row.signal_status or 'entry'
        
        print(f'{status_icon} ID:{row.id} {row.bond_code} {row.bond_name or ""}')
        print(f'   入场: {row.tick_time} @ {row.entry_price}')
        print(f'   阈值: TP={row.take_profit_price}, SL={row.stop_loss_price}, 最大{row.max_hold_time}分钟')
        
        if row.is_locked:
            print(f'   结算: {status_text} | 出场价={row.exit_price} | 收益={row.final_return_pct:.2f}% | 持仓{row.hold_seconds}秒')
            print(f'   原因: {row.lock_reason} | 出场时间={row.exit_time}')
        else:
            print(f'   状态: 持仓中（等待触发）')
        print()
    
    # 生成JSON供前端使用
    print()
    print('='*80)
    print('【JSON格式（供前端API参考）】')
    print('='*80)
    
    hits_json = []
    for row in rows:
        hits_json.append({
            'id': row.id,
            'bond_code': row.bond_code,
            'bond_name': row.bond_name,
            'tick_time': str(row.tick_time),
            'entry_price': float(row.entry_price),
            'take_profit_price': float(row.take_profit_price),
            'stop_loss_price': float(row.stop_loss_price),
            'max_hold_time': row.max_hold_time,
            'is_locked': bool(row.is_locked),
            'signal_status': row.signal_status,
            'lock_reason': row.lock_reason,
            'final_return_pct': float(row.final_return_pct) if row.final_return_pct else None,
            'exit_price': float(row.exit_price) if row.exit_price else None,
            'exit_time': str(row.exit_time) if row.exit_time else None,
            'hold_seconds': row.hold_seconds
        })
    
    print(json.dumps({
        'success': True,
        'date': today,
        'count': len(rows),
        'stats': {
            'total': len(rows),
            'settled': len(settled),
            'holding': len(holding),
            'profited': len(profited),
            'stopped': len(stopped),
            'timeout': len(timeout)
        },
        'hits': hits_json
    }, ensure_ascii=False, indent=2))
