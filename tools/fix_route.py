# fix_route.py - Fix buy-points route path
path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = "@monitor_bp.route('/api/monitor/buy-points', methods=['GET'])"
new = "@monitor_bp.route('/buy-points', methods=['GET'])"

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed: /api/monitor/buy-points -> /buy-points')
else:
    print('ERROR: old route not found')
