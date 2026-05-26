"""Debug tick rendering - dump full renderMarketData flow"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()
# Find renderMarketData function boundaries
start = 0
end = 0
for i, line in enumerate(lines, 1):
    if 'function renderMarketData' in line:
        start = i
    if start and i > start and line.strip() == '}':
        end = i
        # Check if this is the function end
        # Print 20 lines to find the tick code snippet
        snippet = '\n'.join(lines[i-10:i+10])
        if 'stock-tick' in snippet or 'tick涨' in snippet:
            break

print(f'renderMarketData: lines {start}-{end}')
print('\nContext around tick code:')
for i in range(max(0, start-1), min(len(lines), end+1)):
    line = lines[i].rstrip()
    marker = '>>>' if 'tick' in line.lower() or 'stock-tick' in line.lower() or 'bond-tick' in line.lower() else '   '
    print(f"{marker} {i+1}: {line[:120]}")
