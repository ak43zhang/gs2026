import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.cls.cn/telegraph',
}

# Check v1 response
r = requests.get('https://www.cls.cn/v1/roll/get_roll_list?app=CailianpressWeb&os=web&sv=8.4.6&rn=20', headers=headers, timeout=10)
data = r.json()
print(f"errno: {data.get('errno')}")
print(f"msg: {data.get('msg')}")
print(f"Full: {json.dumps(data, ensure_ascii=False)[:500]}")

print()

# Try v3
r2 = requests.get('https://www.cls.cn/v3/roll/get_roll_list?app=CailianpressWeb&os=web&sv=8.4.6&rn=20', headers=headers, timeout=10)
data2 = r2.json()
print(f"v3 errno: {data2.get('errno')}")
print(f"v3 msg: {data2.get('msg')}")
print(f"v3 Full: {json.dumps(data2, ensure_ascii=False)[:500]}")
