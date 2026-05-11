"""Migrate existing todo_items: add priority=2 to items missing it."""
import json
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
url = url.replace('charset=utf8&', 'charset=utf8mb4&')
if 'charset=' not in url:
    url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
engine = create_engine(url)

updated = 0
with engine.connect() as conn:
    r = conn.execute(text('SELECT id, todo_items FROM user_journals WHERE todo_items IS NOT NULL'))
    rows = r.fetchall()
    for row in rows:
        rid, raw = row[0], row[1]
        if not raw:
            continue
        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(items, list):
            continue
        changed = False
        for item in items:
            if isinstance(item, dict) and 'priority' not in item:
                item['priority'] = 2
                changed = True
        if changed:
            conn.execute(
                text('UPDATE user_journals SET todo_items = :t WHERE id = :id'),
                {'t': json.dumps(items, ensure_ascii=False), 'id': rid}
            )
            updated += 1
    conn.commit()

print(f'OK: Migrated {updated} journals (added priority field)')
