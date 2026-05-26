"""
插入300763测试数据
"""
from sqlalchemy import create_engine, text
import json

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

test_record = {
    'date': '2026-05-19',
    'time': '09:30:21',
    'stock_code': '300763',
    'stock_name': '锦浪科技',
    'stock_price': 68.50,
    'stock_change_pct': 3.25,
    'bond_code': '123456',
    'bond_price': 135.80,
    'bond_change_pct': 2.15,
    'level': 3,
    'condition_count': 3,
    'total_conditions': 3,
    'conditions': json.dumps([
        {'name': '主力净额/峰值', 'passed': True},
        {'name': '行业排行', 'passed': True},
        {'name': '涨幅条件', 'passed': True}
    ]),
    'market_context': json.dumps({
        'signal': '强势',
        'passed': 3,
        'total': 3
    })
}

with engine.connect() as conn:
    sql = """
        INSERT INTO buy_point_candidates 
        (date, time, stock_code, stock_name, stock_price, stock_change_pct,
         bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
         conditions, market_context)
        VALUES (:date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
         :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
         :conditions, :market_context)
        ON DUPLICATE KEY UPDATE
        stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
        bond_price=VALUES(bond_price), bond_change_pct=VALUES(bond_change_pct),
        level=VALUES(level), condition_count=VALUES(condition_count),
        conditions=VALUES(conditions), market_context=VALUES(market_context)
    """
    
    conn.execute(text(sql), test_record)
    conn.commit()
    
    # 验证
    result = conn.execute(text("SELECT id, date, time, stock_code, stock_name, level FROM buy_point_candidates WHERE stock_code = '300763'"))
    row = result.fetchone()
    if row:
        print(f"插入成功: ID={row[0]}, {row[3]} {row[4]}, Level={row[5]}")
    else:
        print("插入失败")
