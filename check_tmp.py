import requests
import traceback

# 测试各API
apis = [
    '/api/monitor/timestamps',
    '/api/monitor/attack-ranking/stock',
    '/api/monitor/attack-ranking/bond',
    '/api/monitor/attack-ranking/industry',
    '/api/monitor/market-overview',
    '/api/monitor/latest-messages?check_change=1',
]

for api in apis:
    try:
        r = requests.get(f'http://localhost:8080{api}', timeout=10)
        if r.status_code == 500:
            print(f'500 {api}')
            # 打印错误内容
            try:
                data = r.json()
                print(f'  error: {data.get("error", data.get("message", ""))}')
            except:
                print(f'  body: {r.text[:200]}')
        else:
            print(f'{r.status_code} {api} OK')
    except Exception as e:
        print(f'ERR {api}: {e}')
