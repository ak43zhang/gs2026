import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
url = config_util.get_config('common.url')
engine = create_engine(url)
with engine.connect() as conn:
    # 检查索引
    result = conn.execute(text("SHOW INDEX FROM stock_anomaly"))
    for row in result.fetchall():
        print(f"{row[2]:30s} | {row[4]:20s} | {row[10]}")
    
    print("\n--- 表大小 ---")
    result = conn.execute(text("SELECT COUNT(*) FROM stock_anomaly WHERE trading_date = '2026-06-25'"))
    print(f"今日数据量: {result.scalar()}")
    
    result = conn.execute(text("SELECT COUNT(*) FROM stock_anomaly"))
    print(f"总数据量: {result.scalar()}")
