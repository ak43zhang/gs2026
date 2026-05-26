# fix_buypoints_js.py - Move buy-points JS inside <script> tag
import sys

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print(f'Original: {len(lines)} lines')

# 1. Find the standalone buy-points JS section (outside <script>)
# It's between "    </script>" and "    <script src=..."
js_start = None
js_end = None

for i in range(len(lines) - 1):
    # buy-points JS starts with the comment
    if '// === 买点候选' in lines[i] and 'buy-points-panel' not in lines[i]:
        js_start = i
    if js_start is not None and 'perf-monitor.js' in lines[i]:
        js_end = i
        break

print(f'buy-points JS: lines {js_start+1} to {js_end}')
print(f'Before JS: ...{lines[js_start-2].rstrip()} | {lines[js_start-1].rstrip()}')
print(f'After JS: ...{lines[js_end].rstrip()} | {lines[js_end+1].rstrip()}')

# Extract buy-points JS block
buy_js = lines[js_start:js_end]
print(f'Extracted {len(buy_js)} lines')

# Remove from original
new_lines = lines[:js_start] + lines[js_end:]

# Now find the "    </script>" before the buy-points section was
# and insert buy-js before it
target_close = None
for i in range(len(new_lines) - 1, js_start, -1):
    stripped = new_lines[i].strip()
    if stripped == '</script>' and 'perf-monitor.js' not in new_lines[i]:
        target_close = i
        break

print(f'Will insert before </script> at line {target_close+1}')
print(f'Context: {new_lines[target_close-1].rstrip() if target_close > 0 else "?"}')
print(f'Target: {new_lines[target_close].rstrip()}')

# Insert closing script before target_close, then buy-js, then keep the old </script>
buy_js.insert(0, '    </script>\n')
buy_js.insert(1, '\n')
# Add opening script tag at end
buy_js.append('    <script>\n')

new_lines = new_lines[:target_close] + buy_js + new_lines[target_close+1:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Done. New file: {len(new_lines)} lines')

# Verify
with open(path, 'r', encoding='utf-8-sig') as f:
    c = f.read()
if 'buy-points-panel' in c:
    ss_count = c.count('<script>') + c.count('<script ')
    sc_count = c.count('</script>')
    print(f'<script> count: {ss_count}, </script> count: {sc_count}')
    # Find buy-js location
    for i, l in enumerate(c.split('\n')):
        if '买点候选' in l:
            print(f'  buy-points comment at line {i+1}')
    for i, l in enumerate(c.split('\n')):
        if 'function updateBuyPoints' in l:
            print(f'  updateBuyPoints at line {i+1}')
