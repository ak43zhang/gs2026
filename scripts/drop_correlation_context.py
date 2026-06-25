import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
url = config_util.get_config('common.url')
engine = create_engine(url)
with engine.connect() as conn:
    # 检查字段是否存在
    result = conn.execute(text("SHOW COLUMNS FROM stock_anomaly WHERE Field = 'correlation_context'"))
    rows = result.fetchall()
    if rows:
        conn.execute(text("ALTER TABLE stock_anomaly DROP COLUMN correlation_context"))
        conn.commit()
        print("[OK] 已删除 correlation_context 字段")
    else:
        print("[OK] correlation_context 字段已不存在")
