#!/usr/bin/env python
"""检查 Flask 返回的 HTML 内容"""
import urllib.request

r = urllib.request.urlopen('http://localhost:8080/analysis/backtest')
html = r.read().decode('utf-8')

# 查找 .stars 相关的 CSS
idx = html.find('.data-table .stars')
if idx >= 0:
    snippet = html[idx:idx+500]
    print(f"Found '.data-table .stars' at pos {idx}")
    print(f"Snippet:\n{snippet[:300]}")
else:
    print("'.data-table .stars' NOT found")

print()

# 查找 renderRecords 函数
idx2 = html.find('renderRecords')
if idx2 >= 0:
    snippet2 = html[idx2:idx2+800]
    print(f"Found 'renderRecords' at pos {idx2}")
    print(f"Snippet:\n{snippet2[:500]}")
else:
    print("'renderRecords' NOT found")

print()
print(f"Total HTML length: {len(html)}")
print(f"File on disk check:")
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\backtest.html', 'r', encoding='utf-8') as f:
    disk_html = f.read()
print(f"  Disk file length: {len(disk_html)}")
print(f"  Served HTML length: {len(html)}")
print(f"  Match: {html == disk_html}")
