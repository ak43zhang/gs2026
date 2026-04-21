#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""排查8080端口的涨停分析API"""
import urllib.request
import urllib.error
import json
import ssl

# 禁用SSL验证（如果有）
ssl._create_default_https_context = ssl._create_unverified_context

def test_api(url, desc):
    print(f"\n【测试】{desc}")
    print(f"URL: {url}")
    print("-" * 40)
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"状态码: {resp.status}")
            print(f"返回code: {data.get('code')}")
            print(f"返回message: {data.get('message')}")
            if data.get('code') == 0:
                items = data.get('data', {}).get('items', [])
                total = data.get('data', {}).get('total', 0)
                print(f"数据条数: {len(items)}")
                print(f"总数: {total}")
                if items:
                    print(f"第一条: {items[0].get('stock_name')} ({items[0].get('stock_code')})")
                return True
            else:
                print(f"❌ API返回错误: {data.get('message')}")
                return False
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP错误: {e.code} - {e.reason}")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

print("=" * 60)
print("排查8080端口涨停分析API")
print("=" * 60)

base_url = "http://localhost:8080"

# 测试1: 列表API
test_api(f"{base_url}/api/ztb/list?date=20260413&page=1&page_size=5", "涨停列表API")

# 测试2: 统计API
test_api(f"{base_url}/api/ztb/stats?date=20260413", "涨停统计API")

print("\n" + "=" * 60)
print("排查完成")
print("=" * 60)
