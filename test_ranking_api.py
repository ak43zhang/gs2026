"""检查股票上攻排行API"""
import requests
import time

url = 'http://localhost:8080/api/monitor/stock-ranking?limit=60'

print(f"测试: {url}")
start = time.time()
try:
    response = requests.get(url, timeout=30)
    elapsed = time.time() - start
    print(f"状态: {response.status_code}, 耗时: {elapsed:.2f}s")
    print(f"内容长度: {len(response.text)}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(f"success: {data.get('success')}")
            print(f"count: {data.get('count')}")
            print(f"type: {data.get('type')}")
            print(f"mode: {data.get('mode')}")
            print(f"time: {data.get('time')}")
            if data.get('data'):
                print(f"第一条: {data['data'][0]}")
        except Exception as e:
            print(f"JSON解析失败: {e}")
            print(f"响应内容前500: {response.text[:500]}")
    else:
        print(f"响应: {response.text[:500]}")
except Exception as e:
    print(f"请求失败: {e}")
