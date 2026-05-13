"""测试正确的API端点"""
import requests
import time

# 正确的端点
urls = [
    'http://localhost:8080/api/monitor/attack-ranking/stock?limit=60',
    'http://localhost:8080/api/monitor/attack-ranking/stock?date=2026-05-12&time=13:45:00',
]

for url in urls:
    print(f"\n测试: {url}")
    start = time.time()
    try:
        response = requests.get(url, timeout=30)
        elapsed = time.time() - start
        print(f"状态: {response.status_code}, 耗时: {elapsed:.2f}s")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"success: {data.get('success')}")
                print(f"count: {data.get('count')}")
                print(f"type: {data.get('type')}")
                print(f"mode: {data.get('mode')}")
            except Exception as e:
                print(f"JSON解析失败: {e}")
                print(f"响应前200: {response.text[:200]}")
        else:
            print(f"响应: {response.text[:200]}")
    except Exception as e:
        print(f"请求失败: {e}")
