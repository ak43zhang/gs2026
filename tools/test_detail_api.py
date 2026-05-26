"""
测试详情API
"""
from sqlalchemy import create_engine, text
import json

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 获取一条测试数据
    result = conn.execute(text("SELECT id, stock_code, stock_name FROM buy_point_candidates LIMIT 1"))
    row = result.fetchone()
    if row:
        print(f"ID={row[0]}, Code={row[1]}, Name={row[2]}")
        
        # 测试详情查询
        result = conn.execute(text("SELECT * FROM buy_point_candidates WHERE id = :id"), {'id': row[0]})
        columns = result.keys()
        data = dict(zip(columns, result.fetchone()))
        
        # 转换
        if data.get('date'):
            data['date'] = str(data['date'])
        if data.get('time'):
            if hasattr(data['time'], 'total_seconds'):
                total_seconds = int(data['time'].total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                data['time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        print(f"\n详情数据:")
        print(json.dumps(data, indent=2, default=str))
    else:
        print("No data")
