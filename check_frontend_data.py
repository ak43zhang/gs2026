"""检查前端过滤逻辑"""
import requests

# 获取原始数据
url = 'http://localhost:8080/api/monitor/attack-ranking/stock?limit=60'
response = requests.get(url, timeout=30)
data = response.json()

print(f"API返回: success={data.get('success')}, count={data.get('count')}")
print(f"数据条数: {len(data.get('data', []))}")

# 检查是否有行业字段
if data.get('data'):
    first = data['data'][0]
    print(f"\n第一条数据字段:")
    for k, v in first.items():
        print(f"  {k}: {v}")
    
    # 检查industry_name字段
    print(f"\nindustry_name: '{first.get('industry_name')}'")
    
    # 统计行业分布
    from collections import Counter
    industries = [d.get('industry_name', '') for d in data['data']]
    print(f"\n行业分布:")
    for name, count in Counter(industries).most_common(10):
        print(f"  {name}: {count}")
