#!/usr/bin/env python
"""检查服务器返回的 backtest.html 是否包含 star_color 逻辑"""
import urllib.request

url = 'http://localhost:8080/analysis/backtest'
r = urllib.request.urlopen(url)
html = r.read().decode('utf-8')

checks = [
    ('star-critical CSS', 'star-critical'),
    ('star_color JS', 'row.star_color'),
    ('starClass JS', 'starClass'),
]

for name, pattern in checks:
    found = pattern in html
    print(f"{'[OK]' if found else '[MISSING]'} {name}: {pattern}")

if 'star-critical' not in html:
    print("\n!!! Server is NOT serving the updated backtest.html !!!")
    print("Flask template cache may be stale.")
else:
    print("\nServer IS serving updated HTML. Browser cache is the issue.")
    print("\nFix: Open in incognito window (Ctrl+Shift+N) then go to:")
    print("  http://localhost:8080/analysis/backtest")
