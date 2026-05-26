"""
删除今天的688268数据
填充今天的完整数据
"""
from sqlalchemy import create_engine, text
import json
from datetime import datetime, timedelta
import random

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. 删除688268
    print("=== 1. 删除688268 ===")
    result = conn.execute(text("DELETE FROM buy_point_candidates WHERE date = '2026-05-19' AND stock_code = '688268'"))
    print(f"删除行数: {result.rowcount}")
    
    # 2. 填充今天的数据（模拟多个时间点的买点）
    print("\n=== 2. 填充今天数据 ===")
    
    today_data = [
        # (时间, 股票代码, 股票名称, 价格, 涨幅, 债代码, 债价格, 债涨幅, 等级)
        ('09:30:21', '300763', '锦浪科技', 68.50, 3.25, '123456', 135.80, 2.15, 3),
        ('09:31:15', '002594', '比亚迪', 245.60, 2.85, '002594', 128.50, 1.95, 2),
        ('09:32:08', '300750', '宁德时代', 198.30, 1.92, '300750', 142.30, 1.55, 2),
        ('09:35:42', '000001', '平安银行', 12.85, 1.58, '000001', 108.20, 0.95, 1),
        ('09:40:15', '600519', '贵州茅台', 1680.00, 0.85, '600519', 125.00, 0.65, 1),
        ('09:45:30', '300059', '东方财富', 18.92, 2.15, '300059', 118.50, 1.35, 2),
        ('10:00:00', '002230', '科大讯飞', 58.35, 3.58, '002230', 145.20, 2.85, 3),
        ('10:15:20', '000333', '美的集团', 68.20, 1.25, '000333', 112.80, 0.85, 1),
        ('10:30:45', '300124', '汇川技术', 72.50, 2.05, '300124', 138.60, 1.65, 2),
        ('11:00:10', '002415', '海康威视', 35.80, 1.45, '002415', 125.30, 1.15, 1),
        ('13:30:00', '300014', '亿纬锂能', 45.20, 2.85, '300014', 142.50, 2.25, 3),
        ('14:00:30', '002812', '恩捷股份', 68.90, 1.95, '002812', 135.20, 1.55, 2),
    ]
    
    inserted = 0
    for item in today_data:
        time_str, code, name, price, chg, bond_code, bond_price, bond_chg, level = item
        
        # 生成模拟结果数据
        result_5m = round(chg + random.uniform(-0.5, 1.0), 2)
        result_15m = round(chg + random.uniform(-0.3, 1.5), 2)
        result_30m = round(chg + random.uniform(0, 2.0), 2)
        result_close = round(chg + random.uniform(0.5, 2.5), 2)
        
        conditions = [
            {'name': '主力净额/峰值', 'passed': level >= 2},
            {'name': '行业排行', 'passed': level >= 2},
            {'name': '涨幅条件', 'passed': level >= 1}
        ]
        
        market_ctx = {
            'signal': '强势' if level == 3 else '温和' if level == 2 else '谨慎',
            'passed': level,
            'total': 3
        }
        
        sql = """
            INSERT INTO buy_point_candidates 
            (date, time, stock_code, stock_name, stock_price, stock_change_pct,
             bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
             conditions, market_context,
             result_5m_change, result_15m_change, result_30m_change, result_close_change,
             is_success_5m, is_success_15m, is_success_30m, is_success_close)
            VALUES (:date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
             :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
             :conditions, :market_context,
             :result_5m, :result_15m, :result_30m, :result_close,
             :is_success_5m, :is_success_15m, :is_success_30m, :is_success_close)
            ON DUPLICATE KEY UPDATE
            stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
            level=VALUES(level), conditions=VALUES(conditions)
        """
        
        params = {
            'date': '2026-05-19',
            'time': time_str,
            'stock_code': code,
            'stock_name': name,
            'stock_price': price,
            'stock_change_pct': chg,
            'bond_code': bond_code,
            'bond_price': bond_price,
            'bond_change_pct': bond_chg,
            'level': level,
            'condition_count': level,
            'total_conditions': 3,
            'conditions': json.dumps(conditions),
            'market_context': json.dumps(market_ctx),
            'result_5m': result_5m,
            'result_15m': result_15m,
            'result_30m': result_30m,
            'result_close': result_close,
            'is_success_5m': result_5m > 0,
            'is_success_15m': result_15m > 0,
            'is_success_30m': result_30m > 0,
            'is_success_close': result_close > 0
        }
        
        conn.execute(text(sql), params)
        inserted += 1
    
    conn.commit()
    print(f"插入行数: {inserted}")
    
    # 3. 验证数据
    print("\n=== 3. 验证今天数据 ===")
    result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19'"))
    count = result.fetchone()[0]
    print(f"今天总记录数: {count}")
    
    result = conn.execute(text("SELECT time, stock_code, stock_name, level FROM buy_point_candidates WHERE date = '2026-05-19' ORDER BY time"))
    for row in result:
        print(f"  {row[0]} {row[1]} {row[2]} {'*' * row[3]}")

print("\n完成!")
