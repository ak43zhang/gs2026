#!/usr/bin/env python3
"""
临时方案：直接从数据库读取在用方案，绕过API
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()

with ds.engine.connect() as conn:
    result = conn.execute(text(
        "SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, max_hold_time "
        "FROM quant_screen_schemes WHERE is_active = 1 AND use_replay = 1"
    ))
    
    schemes = []
    for row in result:
        import json
        schemes.append({
            'name': row.scheme_name,
            'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
            'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
            'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
            'max_hold_time': row.max_hold_time
        })
    
    print(f"从数据库加载 {len(schemes)} 个在用方案:")
    for s in schemes:
        print(f"  - {s['name']}")
    
    # 保存到文件供回放脚本使用
    output_file = 'temp/active_schemes.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schemes, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到: {output_file}")
    print(f"\n运行回放脚本时指定: --schemes {output_file}")
