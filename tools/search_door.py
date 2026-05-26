with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Search for door rule related patterns
keywords = ['door', 'rule', 'men', 'gui', 'order', 'sort', 'drag']
for kw in keywords:
    if kw in html.lower():
        idx = html.lower().find(kw)
        print(f'Found "{kw}" at char {idx}')
        print(f'  Context: {repr(html[idx-30:idx+50])}')
        print()
