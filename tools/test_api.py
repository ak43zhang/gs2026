import urllib.request, json

url = 'http://127.0.0.1:8080/api/monitor/buy-points/recent?date=20260521&limit=3'
try:
    req = urllib.request.Request(url, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read().decode())
    print('Success:', data.get('success'))
    print('Items count:', len(data.get('items', [])))
    print('')
    for item in data.get('items', []):
        level = item.get('level')
        print(f"Code: {item.get('stock_code')}")
        print(f"  Name: {item.get('stock_name')}")
        print(f"  Level: {level} (type: {type(level).__name__})")
        print(f"  Hit count: {item.get('hit_count')}")
        print(f"  Time: {item.get('time')}")
        print('')
except Exception as e:
    print('FAIL:', e)
