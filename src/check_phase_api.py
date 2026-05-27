"""检查 market-overview API 返回数据"""
import urllib.request, json

# 先登录
login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
req = urllib.request.Request('http://localhost:8080/login', data=login_data,
                            headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
cookies = resp.headers.get_all('Set-Cookie')
cookie_str = '; '.join([c.split(';')[0] for c in cookies]) if cookies else ''

# 查 market-overview
req2 = urllib.request.Request('http://localhost:8080/api/monitor/market-overview?date=20260527&time=15:00:00')
req2.add_header('Cookie', cookie_str)
resp2 = urllib.request.urlopen(req2)
data = json.loads(resp2.read())

if data.get('success'):
    stock = data.get('data', {}).get('stock', {})
    bond = data.get('data', {}).get('bond', {})
    print("=== 股票 ===")
    for k in ['market_phase', 'phase_strength', 'phase_momentum']:
        print(f"  {k}: {stock.get(k, 'MISSING')}")
    print(f"\n=== 债券 ===")
    for k in ['market_phase', 'phase_strength', 'phase_momentum']:
        print(f"  {k}: {bond.get(k, 'MISSING')}")
    print(f"\n全部字段(股票): {list(stock.keys())}")
else:
    print(f"API 错误: {data}")
