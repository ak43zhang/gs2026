from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
url = url.replace('charset=utf8&', 'charset=utf8mb4&')
if 'charset=' not in url:
    url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
engine = create_engine(url)
with engine.connect() as conn:
    r = conn.execute(text('DESCRIBE user_journals'))
    for row in r:
        print(row)
    print('---')
    r2 = conn.execute(text('SELECT journal_date, content, todo_items, remarks FROM user_journals LIMIT 3'))
    for row in r2:
        print(row)
