with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find renderRecentBp
idx = html.find('function renderRecentBp')
snippet = html[idx:idx+1500]

# Write to file to avoid encoding issues
with open(r'F:\pyworkspace2026\gs2026\tools\render_recent.txt', 'w', encoding='utf-8') as f:
    f.write(snippet)

print('Saved to render_recent.txt, length:', len(snippet))
