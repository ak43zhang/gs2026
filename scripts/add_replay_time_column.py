"""
添加 replay_time 字段到 stock_anomaly_potential 表
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text

# 直接配置数据库连接
DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"

def add_replay_time_column():
    engine = create_engine(DB_URL)
    
    # 检查字段是否已存在
    check_sql = """
        SELECT COUNT(*) FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'stock_anomaly_potential'
        AND COLUMN_NAME = 'replay_time'
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(check_sql))
        count = result.scalar()
        
        if count > 0:
            print("[OK] replay_time 字段已存在")
            return
    
    # 添加字段
    alter_sql = """
        ALTER TABLE stock_anomaly_potential
        ADD COLUMN replay_time TIME NULL COMMENT '复盘时间点，NULL表示实时模式',
        ADD INDEX idx_replay_time (trading_date, replay_time)
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(alter_sql))
            conn.commit()
        print("[OK] 成功添加 replay_time 字段和索引")
    except Exception as e:
        print(f"[ERROR] 添加字段失败: {e}")

if __name__ == '__main__':
    add_replay_time_column()
