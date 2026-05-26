#!/usr/bin/env python
"""检查 API 返回的 star_color 字段"""
import urllib.request
import json

url = 'http://localhost:8080/api/backtest/records'
payload = json.dumps({
    'start_date': '2026-05-19',
    'end_date': '2026-05-19',
    'page': 1,
    'page_size': 10,
    'levels': [1, 2, 3]
}).encode('utf-8')

req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req)
data = json.loads(r.read())

rows = data.get('data', [])
print(f"Total rows: {len(rows)}")
if rows:
    print(f"Keys in first row: {list(rows[0].keys())}")
    print()
    for x in rows:
        print(f"  code={x.get('stock_code')}, level={x.get('level')}, star_color={x.get('star_color')}, time={x.get('time')}")
else:
    print("No data returned")
    print(f"Full response: {data}")
