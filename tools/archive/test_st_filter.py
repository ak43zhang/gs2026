import requests

print('=== 测试ST板块筛选 ===')

# 测试ST板块
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=st')
print(f"Status: {r.status_code}")
data = r.json()
print(f"Response: {data}")
