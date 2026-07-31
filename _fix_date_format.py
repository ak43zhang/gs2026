import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

with open('src/gs2026/dashboard2/routes/monitor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换所有 actual_date = date or datetime.now().strftime('%Y%m%d')
old = "actual_date = date or datetime.now().strftime('%Y%m%d')"
new = "actual_date = (date or datetime.now().strftime('%Y%m%d')).replace('-', '')"

if old in content:
    count = content.count(old)
    print(f'找到 {count} 处需要替换')
    content = content.replace(old, new)
    
    with open('src/gs2026/dashboard2/routes/monitor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'已替换 {count} 处')
else:
    print('未找到匹配文本')
