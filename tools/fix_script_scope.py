# fix_script_scope.py - Move buy-points JS from perf-config script to main script
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Find the buy-points JS block
bp_start_marker = '        // ==================== 买点候选 ===================='
bp_end_marker = "        setTimeout(updateBuyPoints, 1500);"

bp_start = content.find(bp_start_marker)
bp_end = content.find(bp_end_marker)
if bp_start == -1 or bp_end == -1:
    print('ERROR: buy-points JS not found')
    exit(1)

bp_end += len(bp_end_marker)
bp_js = content[bp_start:bp_end]
print(f'Extracted buy-points JS: {len(bp_js)} chars')

# Remove from current location
content = content[:bp_start] + content[bp_end:]
print('Removed from perf-config script block')

# Find the FIRST </script> (end of main script block)
# It's the one that closes the main block containing loadAllData
lines = content.split('\n')
main_script_close = None
for i, l in enumerate(lines):
    if 'function loadAllData' in l:
        # Find the </script> after this
        for j in range(i, len(lines)):
            if lines[j].strip() == '</script>':
                main_script_close = j
                break
        break

if main_script_close is None:
    print('ERROR: main script close not found')
    exit(1)

print(f'Main </script> at line {main_script_close + 1}')

# Insert buy-points JS before the main </script>
lines.insert(main_script_close, '\n' + bp_js + '\n')

content = '\n'.join(lines)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
new_lines = content.split('\n')
print(f'Done. {len(new_lines)} lines')
for i, l in enumerate(new_lines):
    if 'function updateBuyPoints' in l:
        print(f'  updateBuyPoints at line {i+1}')
    if l.strip() == '</script>':
        print(f'  </script> at line {i+1}')
