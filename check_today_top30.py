"""检查今天的top30表数据"""
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
from datetime import datetime

url = config_util.get_config('common.url')
engine = create_engine(url)

today = datetime.now().strftime('%Y%m%d')
table_name = f'monitor_gp_top30_{today}'

with engine.connect() as conn:
    # 检查表是否存在
    result = conn.execute(text(f"SHOW TABLES LIKE '{table_name}'"))
    if not result.fetchone():
        print(f"表 {table_name} 不存在")
    else:
        # 检查总条数
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        total = result.scalar()
        print(f"表 {table_name} 总条数: {total}")
        
        if total > 0:
            # 查看最新时间点的数据
            result = conn.execute(text(f"""
                SELECT time, COUNT(*) as cnt 
                FROM {table_name}
                GROUP BY time
                ORDER BY time DESC
                LIMIT 5
            """))
            print(f"\n最近5个时间点:")
            for row in result:
                print(f"  {row[0]}: {row[1]}条")
            
            # 查看最新一条数据的字段
            result = conn.execute(text(f"""
                SELECT * FROM {table_name}
                ORDER BY time DESC
                LIMIT 1
            """))
            row = result.fetchone()
            print(f"\n最新数据字段:")
            for i, col in enumerate(result.keys()):
                print(f"  {col}: {row[i]}")
        else:
            print("表为空")
