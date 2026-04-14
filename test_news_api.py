#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

url = 'http://localhost:8080/api/news/list?date=20260413&page=1&page_size=3'
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"Code: {data.get('code')}")
        print(f"Message: {data.get('message')}")
        print(f"Data keys: {list(data.keys())}")
        if 'data' in data and data['data']:
            print(f"Data.data keys: {list(data['data'].keys())}")
            print(f"Items count: {len(data['data'].get('items', []))}")
            print(f"Total: {data['data'].get('total', 0)}")
        else:
            print("No data in response")
except Exception as e:
    print(f"Error: {e}")
