import re

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find the actual HTML element with id=bp-recent-list
matches = re.findall(r'id=[\"\']bp-recent-list[\"\']', html)
print(f'bp-recent-list id matches: {len(matches)}')

# Find all div elements
lines = html.split('\n')
for i, line in enumerate(lines):
    if 'bp-recent-list' in line and '<div' in line:
        print(f'Line {i+1}: {line.strip()[:120]}')
        break
else:
    print('No div with bp-recent-list found')
    # Just find any occurrence
    for i, line in enumerate(lines):
        if 'bp-recent-list' in line:
            print(f'Line {i+1}: {line.strip()[:120]}')
            if i > 10:
                break
