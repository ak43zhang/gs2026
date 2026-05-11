from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
url = url.replace('charset=utf8&', 'charset=utf8mb4&')
if 'charset=' not in url:
    url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
engine = create_engine(url)
with engine.connect() as conn:
    r = conn.execute(text("SELECT id, journal_date, todo_items, is_deleted, updated_at FROM user_journals WHERE journal_date = '2026-05-11' ORDER BY id"))
    for row in r:
        print(row)
    print('---')
    # Also check all journals
    r2 = conn.execute(text("SELECT id, journal_date, LEFT(todo_items, 200) as todo_preview, is_deleted FROM user_journals ORDER BY journal_date DESC LIMIT 20"))
    for row in r2:
        print(row)
