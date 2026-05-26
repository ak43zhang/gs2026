# fix_bp_final.py - Move buy-points JS to correct script block
path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print(f'Original: {len(lines)} lines')

# Step 1: Extract and remove buy-points JS block
bp_start = None
bp_end = None
for i, l in enumerate(lines):
    if '// ==================== 买点候选' in l:
        bp_start = i
    if bp_start is not None and 'setTimeout(updateBuyPoints' in l:
        bp_end = i + 1
        break

if bp_start is None or bp_end is None:
    print('ERROR: buy-points JS not found')
    exit(1)

# Also grab any blank lines before
while bp_start > 0 and lines[bp_start - 1].strip() == '':
    bp_start -= 1

bp_js = lines[bp_start:bp_end]
print(f'Extracted buy-points JS: lines {bp_start+1}-{bp_end} ({len(bp_js)} lines)')

# Remove
lines = lines[:bp_start] + lines[bp_end:]
print(f'After removal: {len(lines)} lines')

# Step 2: Find the main script block (contains renderMarketData)
main_script_close = None
for i, l in enumerate(lines):
    if 'function renderMarketData' in l:
        # Found the main script - now find its closing tag
        for j in range(len(lines) - 1, i, -1):
            if lines[j].strip() == '</script>':
                # Check this is the one that closes the main block
                # by verifying there's no other <script> between i and j
                main_script_close = j
                break
        break

if main_script_close is None:
    print('ERROR: cannot find main script closing tag')
    exit(1)

print(f'Main </script> at line {main_script_close+1}')
print(f'Before: {lines[main_script_close-1].rstrip()[:80]}')

# Insert buy-points JS before the closing tag
lines = lines[:main_script_close] + ['\n'] + bp_js + ['\n'] + lines[main_script_close:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Done. New file: {len(lines)} lines')

# Verify
for i, l in enumerate(lines):
    if 'function updateBuyPoints' in l:
        print(f'  updateBuyPoints at line {i+1}')
for i, l in enumerate(lines):
    if '</script>' in l.strip() and l.strip() == '</script>':
        print(f'  </script> at line {i+1}')
