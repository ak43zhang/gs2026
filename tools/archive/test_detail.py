#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

req = urllib.request.Request('http://localhost:8080/api/ztb/detail/82a8fa78cfea9bfd64fa3143e41a18cd?date=20260413')
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f'Code: {data.get("code")}')
        print(f'Message: {data.get("message")}')
        if data.get('data'):
            d = data['data']
            print(f'Keys: {list(d.keys())}')
            print(f'sector_msg type: {type(d.get("sector_msg"))}')
            sm = d.get('sector_msg')
            if sm:
                print(f'sector_msg length: {len(sm)}')
                print(f'sector_msg[0]: {sm[0] if sm else "None"}')
except Exception as e:
    print(f'Error: {e}')
