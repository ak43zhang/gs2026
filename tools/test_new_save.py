"""
使用新的save逻辑模拟填充今日数据
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json, hashlib
from sqlalchemy import create_engine, text
from datetime import datetime

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

# 模拟candidates（和get_buy_points返回的格式一致）
candidates = [
    {
        'code': '300763', 'name': 'test_jinlang', 'price': 68.50,
        'change_pct': 3.25, 'bond_code': '123169', 'bond_price': None, 'bond_chg': None,
        'cond_net_ratio': True, 'cond_industry': True, 'cond_change_pct': False, 'score': 2
    }
]

market_data = {'signal': 'warm', 'passed': 2, 'total': 3}
date = '20260519'
time_str = '09:30:21'

# 日期转换
save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
save_time = time_str or datetime.now().strftime('%H:%M:%S')

sql = """
    INSERT INTO buy_point_candidates 
    (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
     bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
     conditions, market_context)
    VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
     :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
     :conditions, :market_context)
    ON DUPLICATE KEY UPDATE
    stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
    bond_price=VALUES(bond_price), bond_change_pct=VALUES(bond_change_pct),
    level=VALUES(level), condition_count=VALUES(condition_count),
    conditions=VALUES(conditions), market_context=VALUES(market_context)
"""

with engine.connect() as conn:
    for c in candidates:
        code = c.get('code', '')
        record_id = hashlib.md5(f"{code}{save_date}{save_time}".encode()).hexdigest()
        
        score = c.get('score', 0)
        level = 3 if score >= 3 else (2 if score >= 2 else 1)
        
        conds = [
            {'name': 'net_ratio', 'passed': bool(c.get('cond_net_ratio'))},
            {'name': 'industry', 'passed': bool(c.get('cond_industry'))},
            {'name': 'change_pct', 'passed': bool(c.get('cond_change_pct'))}
        ]
        condition_count = sum(1 for x in conds if x['passed'])
        
        market_ctx = {
            'signal': market_data.get('signal', '-'),
            'passed': market_data.get('passed', 0),
            'total': market_data.get('total', 0)
        }
        
        params = {
            'record_id': record_id,
            'date': save_date,
            'time': save_time,
            'stock_code': code,
            'stock_name': c.get('name', ''),
            'stock_price': c.get('price'),
            'stock_change_pct': c.get('change_pct'),
            'bond_code': c.get('bond_code') or '',
            'bond_price': c.get('bond_price'),
            'bond_change_pct': c.get('bond_chg'),
            'level': level,
            'condition_count': condition_count,
            'total_conditions': 3,
            'conditions': json.dumps(conds),
            'market_context': json.dumps(market_ctx)
        }
        
        conn.execute(text(sql), params)
        print(f"Inserted: {code} record_id={record_id[:16]}...")
    
    conn.commit()
    
    # 验证
    result = conn.execute(text("SELECT id, record_id, date, time, stock_code, stock_name, level FROM buy_point_candidates WHERE date = '2026-05-19' ORDER BY time"))
    print("\n2026-05-19 records:")
    for row in result:
        print(f"  ID={row[0]} rid={row[1][:12]}.. {row[2]} {row[3]} {row[4]} {row[5]} Lv{row[6]}")
    
    # 测试幂等性（再次插入相同数据）
    for c in candidates:
        code = c.get('code', '')
        record_id = hashlib.md5(f"{code}{save_date}{save_time}".encode()).hexdigest()
        score = c.get('score', 0)
        level = 3 if score >= 3 else (2 if score >= 2 else 1)
        conds = [{'name': 'test', 'passed': True}]
        market_ctx = {'signal': 'test', 'passed': 0, 'total': 0}
        params = {
            'record_id': record_id, 'date': save_date, 'time': save_time,
            'stock_code': code, 'stock_name': c.get('name', ''),
            'stock_price': 99.99, 'stock_change_pct': 9.99,
            'bond_code': '', 'bond_price': None, 'bond_change_pct': None,
            'level': level, 'condition_count': 1, 'total_conditions': 3,
            'conditions': json.dumps(conds), 'market_context': json.dumps(market_ctx)
        }
        conn.execute(text(sql), params)
    conn.commit()
    
    # 验证幂等性
    result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19' AND stock_code = '300763'"))
    count = result.fetchone()[0]
    print(f"\nIdempotency check: 300763 count={count} (should be 1)")
    
    # 验证价格已更新
    result = conn.execute(text("SELECT stock_price FROM buy_point_candidates WHERE date = '2026-05-19' AND stock_code = '300763'"))
    price = result.fetchone()[0]
    print(f"Updated price: {price} (should be 99.99)")

print("\nDone!")
