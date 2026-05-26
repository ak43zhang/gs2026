with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    html = f.read()

idx = html.find('function renderRecentBp')
with open(r'F:\pyworkspace2026\gs2026\tools\render_recent.txt', 'w', encoding='utf-8') as f:
    f.write(html[idx:idx+1000])

print('Saved to render_recent.txt')
