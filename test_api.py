"""Test API response for stock ranking"""
import requests
import json

# Test the API
try:
    url = 'http://localhost:5000/api/monitor/attack-ranking/stock?limit=10'
    response = requests.get(url, timeout=10)
    data = response.json()
    
    if data.get('success') and data.get('data'):
        print(f"Total records: {len(data['data'])}")
        print("\nFirst 3 records:")
        for i, item in enumerate(data['data'][:3]):
            print(f"\n{i+1}. Code: {item.get('code')}")
            print(f"   Name: {item.get('name')}")
            print(f"   Count: {item.get('count')}")
            print(f"   Change_pct: {item.get('change_pct')}")
            print(f"   Main_net_amount: {item.get('main_net_amount')}")
            print(f"   Has main_net_amount: {'main_net_amount' in item}")
    else:
        print(f"API error: {data}")
except Exception as e:
    print(f"Error: {e}")
