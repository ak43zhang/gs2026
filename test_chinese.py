#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

req = urllib.request.Request('http://localhost:8080/api/ztb/list?date=20260413&page=1&page_size=3')
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f'Code: {data.get("code")}')
        print(f'Message: {data.get("message")}')
        print(f'Items: {len(data.get("data", {}).get("items", []))}')
        for item in data.get('data', {}).get('items', [])[:3]:
            name = item.get('stock_name', '')
            code = item.get('stock_code', '')
            print(f'  - {name} ({code})')
except Exception as e:
    print(f'Error: {e}')
