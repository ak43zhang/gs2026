#!/usr/bin/env python3
"""
直接运行回放，不依赖HTTP API
通过直接导入函数获取方案
"""
import sys
import os
import asyncio

# 添加项目路径
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(project_root, 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

async def main():
    from datetime import datetime
    
    # 直接从数据库获取在用方案
    print("[加载] 从MySQL数据库获取在用方案...")
    ds = DataService()
    
    schemes = []
    with ds.engine.connect() as conn:
        result = conn.execute(text(
            "SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, max_hold_time, price_offset, offset_mode "
            "FROM quant_screen_schemes WHERE is_active = 1 AND use_replay = 1"
        ))
        
        import json
        for row in result:
            schemes.append({
                'name': row.scheme_name,
                'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
                'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                'max_hold_time': row.max_hold_time,
                'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                'offset_mode': row.offset_mode or 'fixed'
            })
    
    if not schemes:
        print("[错误] 数据库中没有在用方案")
        return
    
    print(f"[加载] 成功加载 {len(schemes)} 个方案:")
    for s in schemes:
        print(f"  - {s['name']}")
    
    # 导入并运行回放
    sys.path.insert(0, os.path.join(project_root, 'test'))
    from replay_quant_screen_hits import QuantScreenReplayer
    
    today = datetime.now().strftime('%Y%m%d')
    replayer = QuantScreenReplayer(mode='mock')
    
    result = await replayer.replay(
        trade_date=today,
        time_start='093000',
        time_end='150000',
        speed='0',
        schemes=schemes
    )
    
    print(f"\n{'='*70}")
    print(f"[完成] 回放结束")
    print(f"{'='*70}")
    print(f"总tick数: {result['total_ticks']}")
    print(f"总命中: {result['summary']['total_matches']}")

if __name__ == '__main__':
    asyncio.run(main())
