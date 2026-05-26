# fix_layout_v3b.py - Fix broken HTML + put buy-points in top-section grid
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print(f'Original: {len(lines)} lines')

# Step 1: Find markers
bp_comment = None
ranking_comment = None
top_section_start = None

for i, l in enumerate(lines):
    if 'class="top-section"' in l and '<div' in l:
        top_section_start = i
    if '<!-- ' in l and '买点' in l:
        bp_comment = i
    if '<!-- ' in l and '排行榜' in l:
        ranking_comment = i

print(f'top-section at {top_section_start+1}, buy-points at {bp_comment+1}, ranking at {ranking_comment+1}')

# Step 2: Extract combine-card from the broken region
combine_start = None
combine_end = None
for i in range(bp_comment, ranking_comment):
    if 'combine-card' in lines[i] and '<div' in lines[i] and 'class=' in lines[i]:
        combine_start = i
    if combine_start is not None and combine_start != i:
        if '</div>' in lines[i]:
            # Count depth
            depth = 0
            for j in range(combine_start, i + 1):
                depth += lines[j].count('<div')
                depth -= lines[j].count('</div>')
            if depth <= 0:
                combine_end = i + 1
                break

if combine_start and combine_end:
    combine_block = lines[combine_start:combine_end]
    print(f'combine-card: lines {combine_start+1}-{combine_end} ({len(combine_block)} lines)')
else:
    print('ERROR: combine-card not found in region')
    exit(1)

# Step 3: Build clean replacement block
new_block = []
new_block.append('\n')
new_block.append('            <!-- 买点候选 -->\n')
new_block.append('            <div class="buy-points-panel" id="buy-points-panel" style="display:none;">\n')
new_block.append('                <h2>🎯 买点候选 <span id="buy-points-count" style="font-size:12px;color:#999;font-weight:normal;"></span></h2>\n')
new_block.append('                <div id="buy-points-market" class="buy-market-conditions"></div>\n')
new_block.append('                <div id="buy-points-list" class="buy-points-list"></div>\n')
new_block.append('            </div>\n')
new_block.append('\n')
for cl in combine_block:
    new_block.append(cl)
new_block.append('\n')

# Step 4: Replace the broken region
# Remove everything from bp_comment to ranking_comment, insert new_block
lines = lines[:bp_comment] + new_block + lines[ranking_comment:]

print(f'Replaced region with {len(new_block)} lines')

# Step 5: Fix CSS
content = ''.join(lines)

# Fix top-section grid
import re
# Find the .top-section line with grid-template-columns
m = re.search(r'\.top-section\s*\{[^}]*grid-template-columns:\s*([^;]+);', content)
if m:
    old_cols = m.group(1).strip()
    print(f'Current top-section columns: {old_cols}')
    content = content.replace(f'grid-template-columns: {old_cols}', 'grid-template-columns: 3fr 2fr 2fr', 1)
    print('CSS: top-section grid -> 3fr 2fr 2fr')
else:
    print('WARNING: top-section grid not found')

# Fix buy-points-panel CSS
old_bp = '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); border-left: 3px solid #667eea; margin-bottom: 10px; }'
new_bp = '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }'
if old_bp in content:
    content = content.replace(old_bp, new_bp)
    print('CSS: buy-points style unified')

# Also try without border-left
old_bp2 = '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }'
# This is already what we want, skip

# Add h2 style for buy-points
old_header = '.buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #333; }'
new_header = '.buy-points-panel h2 { font-size: 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }\n        .buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #333; }'
if old_header in content:
    content = content.replace(old_header, new_header)
    print('CSS: Added h2 style for buy-points')

# Fix responsive: add 3-col breakpoint
old_responsive = '.top-section { grid-template-columns: 1fr; }'
new_responsive = '.top-section { grid-template-columns: 1fr; }  /* stack on small screens */'
# Keep existing responsive as-is

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

final_lines = content.split('\n')
print(f'\nDone. {len(final_lines)} lines')

# Verify structure
for i, l in enumerate(final_lines):
    if 'top-section' in l and '<div' in l and 'class=' in l:
        print(f'  top-section at line {i+1}')
    if 'buy-points-panel' in l and '<div' in l and 'id=' in l:
        print(f'  buy-points-panel at line {i+1}')
    if 'combine-card' in l and '<div' in l and 'class=' in l:
        print(f'  combine-card at line {i+1}')
    if 'ranking-grid' in l and '<div' in l:
        print(f'  ranking-grid at line {i+1}')
