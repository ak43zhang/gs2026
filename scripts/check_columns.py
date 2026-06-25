import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
url = config_util.get_config('common.url')
engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute(text("SHOW COLUMNS FROM analysis_news_detail_2026 WHERE Field LIKE 'expectation%%'"))
    for row in result.fetchall():
        print(row)
