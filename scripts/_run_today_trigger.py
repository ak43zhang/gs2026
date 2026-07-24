# -*- coding: utf-8 -*-
"""
运行今日触发判定，更新应结算的记录
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config
from gs2026.monitor.monitor_bond import _track_pending_exits

engine = create_engine(Config.MYSQL_URI)
today = '20260723'

print('开始运行今日触发判定...')
print(f'日期: {today}')

# 获取当前时间（假设现在交易时段）
from datetime import datetime
current_time = datetime.now().strftime('%H:%M:%S')
print(f'当前时间: {current_time}')

# 查询今日所有未结算记录
with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT id, bond_code, tick_time, entry_price, 
               take_profit_price, stop_loss_price, max_hold_time
        FROM quant_screen_hits 
        WHERE trade_date = :date AND is_locked = 0
    '''), {'date': today})
    pending = result.fetchall()
    print(f'未结算记录: {len(pending)} 条')
    
    if pending:
        print('\n前5条未结算记录:')
        for row in pending[:5]:
            print(f'  {row.bond_code}: entry={row.entry_price}, TP={row.take_profit_price}, SL={row.stop_loss_price}')

# 获取当前行情数据（从数据库最新tick）
# 表名是 monitor_zq_sssj_YYYYMMDD，没有trade_date字段
table_name = f'monitor_zq_sssj_{today}'

try:
    with engine.connect() as conn:
        # 先检查表是否存在
        result = conn.execute(text(f'''
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = :table
        '''), {'table': table_name})
        if result.fetchone()[0] == 0:
            print(f'警告: 表 {table_name} 不存在')
            # 使用模拟数据
            df_data = []
        else:
            # 获取最新时间
            result = conn.execute(text(f'SELECT MAX(time) as max_time FROM {table_name}'))
            max_time = result.fetchone()[0]
            print(f'最新tick时间: {max_time}')
            
            # 获取该时间的所有记录
            result = conn.execute(text(f'''
                SELECT bond_code, price FROM {table_name} WHERE time = :max_time
            '''), {'max_time': max_time})
            price_rows = result.fetchall()
            
            df_data = [{'bond_code': row.bond_code, 'price': float(row.price)} for row in price_rows]
            print(f'获取到 {len(df_data)} 条价格数据')
except Exception as e:
    print(f'获取行情数据失败: {e}')
    df_data = []

if not df_data:
    print('使用模拟数据进行测试...')
    # 使用模拟数据：假设TEST001涨到104（触发止盈）
    df_data = [
        {'bond_code': 'TEST001', 'price': 104.0},
        {'bond_code': 'TEST002', 'price': 97.0},
    ]

df = pd.DataFrame(df_data)

print(f'\n行情样本:')
for _, row in df.head(5).iterrows():
    print(f'  {row["bond_code"]}: {row["price"]}')

# 运行触发判定
print(f'\n运行触发判定...')
_track_pending_exits(df, today, current_time, engine)

# 检查更新后的状态
with engine.connect() as conn:
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
    print(f'\n更新后统计:')
    print(f'  总记录: {row.total}')
    print(f'  已结算: {row.settled}')
    print(f'  持仓中: {row.holding}')
    print(f'  止盈: {row.profited}')
    print(f'  止损: {row.stopped}')
    print(f'  超时: {row.timeout}')
    
    # 显示已结算的记录
    if row.settled and row.settled > 0:
        print(f'\n已结算记录详情:')
        result = conn.execute(text('''
            SELECT id, bond_code, tick_time, entry_price, exit_price,
                   signal_status, lock_reason, final_return_pct, hold_seconds
            FROM quant_screen_hits 
            WHERE trade_date = :date AND is_locked = 1
            ORDER BY id DESC
        '''), {'date': today})
        for r in result:
            print(f'  {r.bond_code}: {r.signal_status} profit={r.final_return_pct:.2f}% hold={r.hold_seconds}s')

print('\n完成！')
