import sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()
checks = [
    ('body overflow:hidden', lambda s: 'body' in s and 'overflow: hidden' in s),
    ('container 100vh', lambda s: '.container' in s and '100vh' in s),
    ('container flex-direction', lambda s: '.container' in s and 'flex-direction: column' in s),
    ('top-section flex-shrink', lambda s: '.top-section' in s and 'flex-shrink: 0' in s),
    ('ranking-grid flex:1', lambda s: '.ranking-grid' in s and 'flex: 1' in s),
    ('ranking-card overflow:hidden', lambda s: '.ranking-card' in s and 'overflow: hidden' in s),
    ('ranking-scroll flex:1', lambda s: '.ranking-scroll' in s and 'flex: 1' in s),
]
for name, check in checks:
    found = any(check(l) for l in lines)
    status = 'OK' if found else 'MISSING'
    print(f'{status}: {name}')
