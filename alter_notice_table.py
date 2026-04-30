import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from sqlalchemy import create_engine, text
from gs2026.utils import config_util

try:
    url = config_util.get_config('common.url')
    print(f"URL: {url[:50]}...")
    engine = create_engine(url)
    
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE analysis_notice_detail_2026 ADD COLUMN notice_category VARCHAR(64) DEFAULT '' COMMENT '公告类型分类' AFTER notice_type"))
        conn.commit()
        print('ALTER TABLE OK')
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
