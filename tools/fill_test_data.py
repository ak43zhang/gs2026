"""
填充2026-05-18历史买点数据
用于测试回溯分析展示效果
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
os.chdir(r'F:\pyworkspace2026\gs2026')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# 从配置读取
from gs2026.utils import config_util
_config = config_util.load_config()
_mysql_config = _config.get('mysql', {})
host = _mysql_config.get('host', '192.168.0.101')
port = _mysql_config.get('port', 3306)
user = _mysql_config.get('user', 'root')
password = _mysql_config.get('password', '123456')
database = _mysql_config.get('database', 'gs')

uri = f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4'
engine = create_engine(uri)

# 测试数据：模拟2026-05-18的买点记录
test_data = [
    # 上午数据
    {'time': '09:35:00', 'stock_code': '000001', 'stock_name': '平安银行', 'stock_price': 12.50, 'stock_change_pct': 2.35, 
     'bond_code': '110032', 'bond_price': 132.50, 'bond_change_pct': 1.20, 'level': 3,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': True}]},
    
    {'time': '09:42:00', 'stock_code': '000002', 'stock_name': '万科A', 'stock_price': 8.20, 'stock_change_pct': 1.85, 
     'bond_code': '110052', 'bond_price': 108.30, 'bond_change_pct': 0.80, 'level': 2,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': False}]},
    
    {'time': '10:15:00', 'stock_code': '000063', 'stock_name': '中兴通讯', 'stock_price': 28.60, 'stock_change_pct': 3.20, 
     'bond_code': '110903', 'bond_price': 145.80, 'bond_change_pct': 2.10, 'level': 3,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': True}]},
    
    {'time': '10:30:00', 'stock_code': '000100', 'stock_name': 'TCL科技', 'stock_price': 4.85, 'stock_change_pct': 1.50, 
     'bond_code': '110905', 'bond_price': 98.50, 'bond_change_pct': 0.60, 'level': 1,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': False}, {'name': '主力净流入', 'passed': False}]},
    
    {'time': '11:05:00', 'stock_code': '000333', 'stock_name': '美的集团', 'stock_price': 68.50, 'stock_change_pct': 2.80, 
     'bond_code': '110906', 'bond_price': 125.60, 'bond_change_pct': 1.50, 'level': 3,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': True}]},
    
    {'time': '11:20:00', 'stock_code': '000538', 'stock_name': '云南白药', 'stock_price': 55.30, 'stock_change_pct': 1.20, 
     'bond_code': '110907', 'bond_price': 112.80, 'bond_change_pct': 0.45, 'level': 2,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': False}]},
    
    # 下午数据
    {'time': '13:30:00', 'stock_code': '000568', 'stock_name': '泸州老窖', 'stock_price': 185.60, 'stock_change_pct': 4.20, 
     'bond_code': '110908', 'bond_price': 168.50, 'bond_change_pct': 2.80, 'level': 3,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': True}]},
    
    {'time': '13:45:00', 'stock_code': '000651', 'stock_name': '格力电器', 'stock_price': 38.20, 'stock_change_pct': 1.90, 
     'bond_code': '110909', 'bond_price': 105.30, 'bond_change_pct': 0.90, 'level': 2,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': False}]},
    
    {'time': '14:10:00', 'stock_code': '000725', 'stock_name': '京东方A', 'stock_price': 4.35, 'stock_change_pct': 2.50, 
     'bond_code': '110910', 'bond_price': 95.60, 'bond_change_pct': 1.20, 'level': 2,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': False}]},
    
    {'time': '14:25:00', 'stock_code': '000768', 'stock_name': '中航西飞', 'stock_price': 28.90, 'stock_change_pct': 3.60, 
     'bond_code': '110911', 'bond_price': 138.40, 'bond_change_pct': 2.30, 'level': 3,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': True}]},
    
    {'time': '14:50:00', 'stock_code': '000858', 'stock_name': '五粮液', 'stock_price': 165.80, 'stock_change_pct': 2.10, 
     'bond_code': '110912', 'bond_price': 152.30, 'bond_change_pct': 1.40, 'level': 2,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': True}, {'name': '主力净流入', 'passed': False}]},
    
    {'time': '15:00:00', 'stock_code': '000895', 'stock_name': '双汇发展', 'stock_price': 26.50, 'stock_change_pct': 1.80, 
     'bond_code': '110913', 'bond_price': 108.90, 'bond_change_pct': 0.85, 'level': 1,
     'conditions': [{'name': '价格突破', 'passed': True}, {'name': '量能放大', 'passed': False}, {'name': '主力净流入', 'passed': False}]},
]

def fill_test_data():
    """填充测试数据"""
    try:
        with engine.connect() as conn:
            for item in test_data:
                # 生成结果数据（模拟5m/15m/30m/收盘结果）
                stock_chg = item['stock_change_pct']
                
                # 模拟后续表现（成功概率70%）
                is_success = random.random() < 0.7
                
                result_5m_change = round(stock_chg + random.uniform(-0.5, 1.5), 2)
                result_15m_change = round(stock_chg + random.uniform(-0.3, 2.0), 2)
                result_30m_change = round(stock_chg + random.uniform(0, 2.5), 2)
                result_close_change = round(stock_chg + random.uniform(0.5, 3.0), 2)
                
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
                     :result_5m_change, :result_15m_change, :result_30m_change, :result_close_change,
                     :is_success_5m, :is_success_15m, :is_success_30m, :is_success_close)
                    ON DUPLICATE KEY UPDATE
                    stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
                    level=VALUES(level), condition_count=VALUES(condition_count),
                    conditions=VALUES(conditions), result_5m_change=VALUES(result_5m_change)
                """
                
                conn.execute(text(sql), {
                    'date': '2026-05-18',
                    'time': item['time'],
                    'stock_code': item['stock_code'],
                    'stock_name': item['stock_name'],
                    'stock_price': item['stock_price'],
                    'stock_change_pct': item['stock_change_pct'],
                    'bond_code': item['bond_code'],
                    'bond_price': item['bond_price'],
                    'bond_change_pct': item['bond_change_pct'],
                    'level': item['level'],
                    'condition_count': sum(1 for c in item['conditions'] if c['passed']),
                    'total_conditions': len(item['conditions']),
                    'conditions': json.dumps(item['conditions']),
                    'market_context': json.dumps({'signal': '温和', 'passed': 2, 'total': 3}),
                    'result_5m_change': result_5m_change,
                    'result_15m_change': result_15m_change,
                    'result_30m_change': result_30m_change,
                    'result_close_change': result_close_change,
                    'is_success_5m': result_5m_change > 0,
                    'is_success_15m': result_15m_change > 0,
                    'is_success_30m': result_30m_change > 0,
                    'is_success_close': result_close_change > 0
                })
            
            conn.commit()
            
            print(f'✅ 成功填充 {len(test_data)} 条测试数据')
            print(f'   日期: 2026-05-18')
            print(f'   数据范围: 09:35 - 15:00')
            print(f'   ⭐⭐⭐: {sum(1 for d in test_data if d["level"]==3)} 条')
            print(f'   ⭐⭐: {sum(1 for d in test_data if d["level"]==2)} 条')
            print(f'   ⭐: {sum(1 for d in test_data if d["level"]==1)} 条')
            
    except Exception as e:
        print(f'❌ 错误: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fill_test_data()
