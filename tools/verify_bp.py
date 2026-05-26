import sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8-sig') as f:
    c = f.read()
count = c.count('runBuyPoints()')
print(f'runBuyPoints() calls: {count}')
old_refs = ['updateBuyPoints', 'getDefaultBpConfig', '_bpConfig']
for ref in old_refs:
    n = c.count(ref)
    if n > 0:
        print(f'WARNING: old ref "{ref}" still found {n} times')
    else:
        print(f'OK: "{ref}" removed')
