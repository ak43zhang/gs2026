"""
修改 stock_anomaly_potential 表的唯一键

从 (trading_date, trigger_time, stock_code) 
改为 (trading_date, replay_time, stock_code)

这样复盘时间点可以保存多个股票，同一时间点重复分析会覆盖旧数据
"""
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"

def fix_unique_key():
    engine = create_engine(DB_URL)
    
    # 删除旧唯一键，添加新唯一键
    sql = """
        -- 删除旧唯一键（如果存在）
        ALTER TABLE stock_anomaly_potential
        DROP INDEX IF EXISTS uk_date_time_code;
        
        -- 添加新唯一键（基于 replay_time）
        ALTER TABLE stock_anomaly_potential
        ADD UNIQUE KEY uk_date_replay_code (trading_date, replay_time, stock_code);
    """
    
    try:
        with engine.connect() as conn:
            # 先检查旧索引是否存在
            check_sql = """
                SELECT COUNT(*) FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'stock_anomaly_potential'
                AND INDEX_NAME = 'uk_date_time_code'
            """
            result = conn.execute(text(check_sql))
            old_exists = result.scalar() > 0
            
            if old_exists:
                # 删除旧索引
                conn.execute(text("ALTER TABLE stock_anomaly_potential DROP INDEX uk_date_time_code"))
                print("[OK] 删除旧唯一键 uk_date_time_code")
            
            # 检查新索引是否已存在
            check_new_sql = """
                SELECT COUNT(*) FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'stock_anomaly_potential'
                AND INDEX_NAME = 'uk_date_replay_code'
            """
            result = conn.execute(text(check_new_sql))
            new_exists = result.scalar() > 0
            
            if not new_exists:
                # 添加新索引
                conn.execute(text("ALTER TABLE stock_anomaly_potential ADD UNIQUE KEY uk_date_replay_code (trading_date, replay_time, stock_code)"))
                print("[OK] 添加新唯一键 uk_date_replay_code (trading_date, replay_time, stock_code)")
            else:
                print("[OK] 新唯一键已存在")
            
            conn.commit()
        print("[OK] 唯一键修改完成")
    except Exception as e:
        print(f"[ERROR] 修改唯一键失败: {e}")

if __name__ == '__main__':
    fix_unique_key()
