"""添加 stock_anomaly 联合索引 - 长超时版本"""
from sqlalchemy import text
from gs2026.utils import config_util

engine = config_util.get_engine()

with engine.connect() as conn:
    # 设置长超时
    conn.execute(text("SET SESSION lock_wait_timeout = 600"))
    conn.execute(text("SET SESSION innodb_lock_wait_timeout = 600"))
    print("开始添加索引（超时600s）...")
    try:
        conn.execute(text("CREATE INDEX idx_status_started ON stock_anomaly (ai_status, ai_started_at)"))
        conn.commit()
        print("索引创建成功!")
        
        result = conn.execute(text("SHOW INDEX FROM stock_anomaly WHERE Key_name = 'idx_status_started'"))
        rows = result.fetchall()
        for r in rows:
            print(f"  列: {r[4]}")
    except Exception as e:
        if 'Duplicate' in str(e):
            print("索引已存在，跳过")
        else:
            print(f"失败: {e}")
