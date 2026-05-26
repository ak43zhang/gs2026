"""
检查当前入库的数据，对比实际应该命中的条件
"""
from sqlalchemy import create_engine, text
import json

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT stock_code, stock_name, stock_price, stock_change_pct, level, condition_count, conditions, bond_code
        FROM buy_point_candidates 
        WHERE date = '2026-05-19' 
        ORDER BY level DESC, stock_change_pct DESC
    """))
    
    rows = result.fetchall()
    print(f"Total: {len(rows)} records\n")
    
    for row in rows[:15]:
        code, name, price, chg, level, cond_cnt, conds_json, bond = row
        conds = json.loads(conds_json) if conds_json else []
        cond_detail = ', '.join([f"{c['name']}={'Y' if c['passed'] else 'N'}" for c in conds])
        bond_mark = f" bond={bond}" if bond else ""
        print(f"  {code} {name} price={price} chg={chg}% Lv{level} ({cond_cnt}/3) [{cond_detail}]{bond_mark}")
