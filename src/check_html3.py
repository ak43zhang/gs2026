#!/usr/bin/env python
"""检查 Flask 返回的实际内容"""
import urllib.request

r = urllib.request.urlopen('http://localhost:8080/analysis/backtest')
html = r.read().decode('utf-8')

print(f"Length: {len(html)}")
print(f"First 500 chars:")
print(html[:500])
print(f"\n...\nLast 200 chars:")
print(html[-200:])
