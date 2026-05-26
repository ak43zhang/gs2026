# check_bp_ids.py
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

html_ids = re.findall(r'id="(bp-[^"]+)"', content)
print('HTML IDs:', sorted(set(html_ids)))

js_ids = re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", content)
bp_js = [x for x in js_ids if x.startswith('bp-')]
print('JS refs:', sorted(set(bp_js)))

missing = set(bp_js) - set(html_ids)
if missing:
    print(f'MISSING in HTML: {missing}')
else:
    print('All JS references match HTML IDs')

# Check if saveBpConfig and onclick are in same script scope
for i, l in enumerate(content.split('\n'), 1):
    if 'saveBpConfig' in l:
        print(f'  Line {i}: {l.strip()[:100]}')
