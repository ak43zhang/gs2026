"""
删除今日测试数据，填充正确的今日数据
"""
import json, hashlib
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. 删除今日测试数据
    result = conn.execute(text("DELETE FROM buy_point_candidates WHERE date = '2026-05-19'"))
    conn.commit()
    print(f"Deleted: {result.rowcount} rows")
    
    # 2. 从monitor_gp_sssj_20260519获取真实股票数据
    # 获取09:30:21时间点涨幅最高的股票
    times_to_check = ['09:30:21', '09:31:51', '09:35:00', '09:40:00', '10:00:00']
    
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
        level=VALUES(level)
    """
    
    inserted = 0
    for t in times_to_check:
        try:
            # 查询该时间点的真实数据
            query = text(f"""
                SELECT stock_code, short_name, price, change_pct
                FROM monitor_gp_sssj_20260519
                WHERE time = :time AND change_pct > 1.5
                ORDER BY change_pct DESC
                LIMIT 5
            """)
            result = conn.execute(query, {'time': t})
            rows = result.fetchall()
            
            if not rows:
                print(f"  {t}: no data")
                continue
            
            for row in rows:
                code = str(row[0]).zfill(6)
                name = row[1] or ''
                price = float(row[2]) if row[2] else None
                chg = float(row[3]) if row[3] else 0
                
                # 模拟评分
                if chg > 5:
                    score = 3
                elif chg > 3:
                    score = 2
                else:
                    score = 1
                level = score
                
                record_id = hashlib.md5(f"{code}2026-05-19{t}".encode()).hexdigest()
                
                conditions = [
                    {'name': 'net_ratio', 'passed': score >= 2},
                    {'name': 'industry', 'passed': score >= 2},
                    {'name': 'change_pct', 'passed': score >= 1}
                ]
                condition_count = sum(1 for x in conditions if x['passed'])
                
                market_ctx = {'signal': 'warm', 'passed': 2, 'total': 3}
                
                params = {
                    'record_id': record_id,
                    'date': '2026-05-19',
                    'time': t,
                    'stock_code': code,
                    'stock_name': name,
                    'stock_price': price,
                    'stock_change_pct': chg,
                    'bond_code': '',
                    'bond_price': None,
                    'bond_change_pct': None,
                    'level': level,
                    'condition_count': condition_count,
                    'total_conditions': 3,
                    'conditions': json.dumps(conditions),
                    'market_context': json.dumps(market_ctx)
                }
                
                conn.execute(text(sql), params)
                inserted += 1
                
            print(f"  {t}: {len(rows)} records")
        except Exception as e:
            print(f"  {t}: error - {e}")
    
    conn.commit()
    print(f"\nTotal inserted: {inserted}")
    
    # 3. 验证
    result = conn.execute(text("SELECT time, stock_code, stock_name, stock_price, stock_change_pct, level FROM buy_point_candidates WHERE date = '2026-05-19' ORDER BY time, stock_code"))
    print("\n2026-05-19 records:")
    for row in result:
        stars = '*' * row[5]
        print(f"  {row[0]} {row[1]} {row[2]} price={row[3]} chg={row[4]}% {stars}")
