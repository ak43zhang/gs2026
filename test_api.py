import urllib.request
import json

url = 'http://localhost:8080/api/monitor/buy-points/generate-effects'
data = {'date': '20260522', 'levels': [1, 2, 3]}

try:
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read().decode())
        print('Success:', result.get('success'))
        print('Filled:', result.get('filled'))
        
        if result.get('details'):
            details = result['details']
            print(f'Total details: {len(details)}')
            
            # 找002859的数据
            for d in details:
                if d['code'] == '002859':
                    print(f"\n002859 {d['name']} (level {d['level']})")
                    print(f"  Time: {d['time']}")
                    print(f"  Stock signal: {d['stock_signal_change_pct']}")
                    print(f"  Stock 5m: {d['stock_5m']}, 15m: {d['stock_15m']}, 30m: {d['stock_30m']}, close: {d['stock_close']}")
                    print(f"  Bond signal: {d['bond_signal_change_pct']}")
                    print(f"  Bond 5m: {d['bond_5m']}, close: {d['bond_close']}")
                    break
        else:
            print('No details')
except Exception as e:
    print('Error:', e)
