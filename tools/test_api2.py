import urllib.request, json

url = 'http://127.0.0.1:8080/api/monitor/buy-points/recent?date=20260521&limit=3'
try:
    req = urllib.request.Request(url, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read().decode())
    print('API返回:')
    print(f'  success: {data.get("success")}')
    print(f'  items数量: {len(data.get("items", []))}')
    for item in data.get('items', []):
        print(f"  {item.get('time')} {item.get('stock_code')} level={item.get('level')}")
except Exception as e:
    print('FAIL:', e)
