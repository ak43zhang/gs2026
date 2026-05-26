"""
手动填充单条买点候选数据到回溯分析表
用于验证保存流程是否正确
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sqlalchemy import create_engine, text
import json
from datetime import datetime

# 数据库配置
MYSQL_HOST = '192.168.0.101'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = '123456'
MYSQL_DATABASE = 'gs'

MYSQL_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# 09:30:21 华特气体买点数据
test_record = {
    'date': '2026-05-19',
    'time': '09:30:21',
    'stock_code': '688268',
    'stock_name': '华特气体',
    'stock_price': 58.35,
    'stock_change_pct': 2.15,
    'bond_code': '118010',  # 华特转债
    'bond_price': 125.50,
    'bond_change_pct': 1.85,
    'level': 2,  # ⭐⭐
    'condition_count': 2,
    'total_conditions': 3,
    'conditions': json.dumps([
        {'name': '主力净额/峰值', 'passed': True},
        {'name': '行业排行', 'passed': True},
        {'name': '涨幅条件', 'passed': False}
    ]),
    'market_context': json.dumps({
        'signal': '温和',
        'passed': 2,
        'total': 3
    })
}

def insert_test_record():
    """插入测试记录"""
    try:
        print(f"正在连接MySQL...")
        engine = create_engine(MYSQL_URI, pool_recycle=3600, pool_pre_ping=True, 
                              connect_args={'connect_timeout': 10})
        
        with engine.connect() as conn:
            print("连接成功")
            
            # 检查表是否存在
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'buy_point_candidates'
            """), {'db': MYSQL_DATABASE})
            
            if result.fetchone()[0] == 0:
                print("表 buy_point_candidates 不存在")
                return
            
            print("表存在")
            
            # 插入数据
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
            
            print("\n数据插入成功!")
            print(f"\n记录详情:")
            print(f"  日期: {test_record['date']}")
            print(f"  时间: {test_record['time']}")
            print(f"  股票: {test_record['stock_code']} {test_record['stock_name']}")
            print(f"  价格: {test_record['stock_price']}")
            print(f"  涨幅: {test_record['stock_change_pct']}%")
            print(f"  等级: {'*' * test_record['level']} ({test_record['level']}星)")
            print(f"  债券: {test_record['bond_code']} (价格: {test_record['bond_price']})")
            
            # 验证插入
            result = conn.execute(text("""
                SELECT COUNT(*) FROM buy_point_candidates 
                WHERE date = :date AND time = :time AND stock_code = :code
            """), {
                'date': test_record['date'],
                'time': test_record['time'],
                'code': test_record['stock_code']
            })
            count = result.fetchone()[0]
            print(f"\n验证: 表中存在 {count} 条匹配记录")
            
            # 查询今日总数
            result = conn.execute(text("""
                SELECT COUNT(*) FROM buy_point_candidates WHERE date = :date
            """), {'date': '2026-05-19'})
            total = result.fetchone()[0]
            print(f"今日({test_record['date']})总记录数: {total}")
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    insert_test_record()
