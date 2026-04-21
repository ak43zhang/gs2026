import requests

print('=== 测试市场筛选 ===')

# 测试全部
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=all')
data = r.json()
print(f"全部: {data['data']['total']}条")

# 测试沪深主板
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=main')
data = r.json()
print(f"沪深主板: {data['data']['total']}条")

# 测试科创板
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=kcb')
data = r.json()
print(f"科创板: {data['data']['total']}条")

# 测试创业板
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=cyb')
data = r.json()
print(f"创业板: {data['data']['total']}条")

# 测试ST板块
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=st')
data = r.json()
print(f"ST板块: {data['data']['total']}条")

# 测试龙虎榜
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=lhb')
data = r.json()
print(f"龙虎榜: {data['data']['total']}条")

# 测试无龙虎榜
r = requests.get('http://localhost:8080/api/ztb/list?date=20260414&market_filter=no_lhb')
data = r.json()
print(f"无龙虎榜: {data['data']['total']}条")
