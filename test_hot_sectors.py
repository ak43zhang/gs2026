import requests

print('=== 新闻分析热点板块 ===')
r = requests.get('http://localhost:8080/api/news/hot-sectors?date=20260413')
data = r.json()
for item in data.get('data', [])[:5]:
    print(f"{item.get('sector')}: {item.get('count')}条, 均分{item.get('avg_score')}")

print('\n=== 领域分析热点板块 ===')
r = requests.get('http://localhost:8080/api/domain/hot-sectors?date=20260413')
data = r.json()
for item in data.get('data', [])[:5]:
    print(f"{item.get('sector')}: {item.get('count')}条, 均分{item.get('avg_score')}")
