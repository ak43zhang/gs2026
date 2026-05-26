#!/usr/bin/env python
"""深入排查 2026-05-19 09:41:33 的 star_color 问题"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import json
import urllib.request

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, connect_args={'connect_timeout': 10})

print("="*60)
print("1. DB record check")
print("="*60)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, stock_code, level, star_color, created_at
        FROM buy_point_candidates 
        WHERE date = '2026-05-19' AND time = '09:41:33' AND stock_code = '600481'
    """))
    for r in result.fetchall():
        print(f"  id={r[0]}, code={r[1]}, level={r[2]}, star_color='{r[3]}', created={r[4]}")

print()
print("="*60)
print("2. API response check")
print("="*60)
payload = json.dumps({
    'start_date': '2026-05-19',
    'end_date': '2026-05-19',
    'page': 1,
    'page_size': 200,
    'levels': [1, 2, 3]
}).encode('utf-8')
req = urllib.request.Request(
    'http://localhost:8080/api/backtest/records',
    data=payload,
    headers={'Content-Type': 'application/json'}
)
r = urllib.request.urlopen(req)
data = json.loads(r.read())
rows = data.get('data', [])

target = [x for x in rows if x.get('stock_code') == '600481' and x.get('time') == '09:41:33']
if target:
    t = target[0]
    print(f"  code={t.get('stock_code')}, level={t.get('level')}, star_color='{t.get('star_color')}', time={t.get('time')}")
    print(f"  All keys with 'star': {[(k,v) for k,v in t.items() if 'star' in k.lower() or 'color' in k.lower()]}")
else:
    print("  NOT FOUND in API response!")
    print(f"  Total rows: {len(rows)}")
    # show first few
    for x in rows[:3]:
        print(f"    code={x.get('stock_code')}, time={x.get('time')}, star_color='{x.get('star_color')}'")

print()
print("="*60)
print("3. HTML template check (server-side)")
print("="*60)
r2 = urllib.request.urlopen('http://localhost:8080/analysis/backtest')
html = r2.read().decode('utf-8')
for pattern in ['star-critical', 'star_color', 'starClass', 'star-normal']:
    idx = html.find(pattern)
    print(f"  '{pattern}': {'FOUND at pos ' + str(idx) if idx >= 0 else 'NOT FOUND'}")
