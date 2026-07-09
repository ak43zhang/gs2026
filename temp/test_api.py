#!/usr/bin/env python3
import requests

api_url = 'http://localhost:8080/api'
try:
    response = requests.get(f'{api_url}/quant-schemes?active_only=1&scene=replay', timeout=5)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"成功: {data.get('success')}")
        schemes = data.get('schemes', [])
        print(f"方案数量: {len(schemes)}")
        for s in schemes:
            print(f"  - {s.get('scheme_name')}")
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")
