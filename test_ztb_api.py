#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试涨停分析API"""
import urllib.request
import json
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def test_api(url, desc):
    print(f"\n【测试】{desc}")
    print(f"URL: {url}")
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Status: {data.get('code')}")
            print(f"Message: {data.get('message')}")
            if data.get('code') == 0:
                items = data.get('data', {}).get('items', [])
                print(f"Items count: {len(items)}")
                if items:
                    print(f"First item keys: {list(items[0].keys())}")
                    print(f"First item: {items[0].get('stock_name')} ({items[0].get('stock_code')})")
                return True, data
            else:
                print(f"Error: {data.get('message')}")
                return False, data
    except Exception as e:
        print(f"Exception: {e}")
        return False, str(e)

print("=" * 60)
print("测试涨停分析API")
print("=" * 60)

base = "http://localhost:8080"

# 测试列表API
success, data = test_api(f"{base}/api/ztb/list?date=20260413&page=1&page_size=3", "涨停列表")

if success and data.get('data', {}).get('items'):
    items = data['data']['items']
    # 测试详情API
    content_hash = items[0].get('content_hash')
    if content_hash:
        test_api(f"{base}/api/ztb/detail/{content_hash}?date=20260413", "涨停详情")

print("\n" + "=" * 60)
