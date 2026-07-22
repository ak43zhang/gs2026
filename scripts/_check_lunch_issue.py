#!/usr/bin/env python3
"""排查回测记录 8393f4b0589e7893 的午休超时问题"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
import json

# 直接连接数据库
engine = create_engine('mysql+pymysql://root:root@localhost:3306/gs2026?charset=utf8mb4')
with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM backtest_history WHERE hash="8393f4b0589e7893"'))
    row = result.fetchone()
    if row:
        print('=== 回测配置 ===')
        print(f"日期: {row.date}")
        print(f"时间范围: {row.time_start} - {row.time_end}")
        print(f"窗口: {row.window_minutes}分钟")
        print(f"TP/SL: {row.tp_pct}% / {row.sl_pct}%")
        print(f"条件数: {len(json.loads(row.conditions)) if row.conditions else 0}")
        print()
        print('=== 交易记录 (前20条) ===')
        trades = json.loads(row.trades) if row.trades else []
        for t in trades[:20]:
            sig = t.get('signal_time', '?')
            exit_t = t.get('exit_time', '?')
            exit_type = t.get('exit_type', '?')
            profit = t.get('profit_pct', 0)
            duration = t.get('duration_sec', 0)
            print(f"  {sig} -> {exit_t} ({exit_type}) 盈亏:{profit}% 持续:{duration}秒")
        
        # 找出11:30附近的交易
        print()
        print('=== 11:30附近的交易 ===')
        for t in trades:
            sig = t.get('signal_time', '')
            if '11:' in sig and int(sig.split(':')[1]) >= 25:
                print(f"  {t.get('signal_time')} -> {t.get('exit_time')} ({t.get('exit_type')}) 盈亏:{t.get('profit_pct')}%")
    else:
        print('记录未找到')
