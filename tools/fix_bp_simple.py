# fix_bp_simple.py - Remove floating JS and re-insert inside script tag
path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

# Step 1: Remove the floating buy-points JS block (outside script)
# It starts with "// ==== 买点候选" and ends with "setTimeout(updateBuyPoints, 1500);\n"
marker_start = '\n        // ==================== 买点候选 ===================='
marker_end = '        setTimeout(updateBuyPoints, 1500);\n'

start_pos = content.find(marker_start)
end_pos = content.find(marker_end)

if start_pos == -1:
    print('ERROR: cannot find buy-points JS start marker')
    exit(1)
if end_pos == -1:
    print('ERROR: cannot find buy-points JS end marker')
    exit(1)

end_pos += len(marker_end)

# Extract the JS block
bp_js = content[start_pos:end_pos]
print(f'Found buy-points JS at chars {start_pos}-{end_pos} ({len(bp_js)} chars)')

# Remove it
content = content[:start_pos] + content[end_pos:]
print('Removed floating JS block')

# Step 2: Find the LAST </script> that's NOT the perf-monitor one
# The main script block ends with </script> before the perf-monitor script
# We want to insert BEFORE that closing tag
import re
# Find all </script> positions
closes = [m.start() for m in re.finditer(r'</script>', content)]
print(f'Found {len(closes)} </script> tags')

# The first </script> is the main script block
if len(closes) < 1:
    print('ERROR: no </script> found')
    exit(1)

# Insert before the first </script>
insert_pos = closes[0]
print(f'Inserting before </script> at position {insert_pos}')
print(f'Context before: ...{content[insert_pos-60:insert_pos]}')

content = content[:insert_pos] + bp_js + '\n' + content[insert_pos:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
lines = content.split('\n')
print(f'Done. {len(lines)} lines')
for i, l in enumerate(lines):
    if 'function updateBuyPoints' in l:
        print(f'  updateBuyPoints at line {i+1}')
    if '</script>' in l and i > 0:
        print(f'  </script> at line {i+1}')
