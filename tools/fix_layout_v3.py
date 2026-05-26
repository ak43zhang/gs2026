# fix_layout_v3.py - Fix broken HTML + put buy-points in top-section grid
import re

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print(f'Original: {len(lines)} lines')

# ===== Step 1: Remove ALL broken buy-points HTML fragments =====
# Remove lines containing buy-points HTML (not CSS, not JS)
# We need to identify the broken structure between market-section closing and ranking-grid

# Find the region between market-section end and ranking-grid
market_end = None
ranking_start = None
for i, l in enumerate(lines):
    if 'class="market-section"' in l:
        # Track where market-section content ends
        pass
    if '<!-- 买点候选 -->' in l:
        market_end = i
    if '<!-- 三个排行榜 -->' in l:
        ranking_start = i
        break

if market_end is None or ranking_start is None:
    # Try alternate markers
    for i, l in enumerate(lines):
        if 'buy-points-panel' in l and 'class=' in l and '<div' in l:
            market_end = i
        if 'ranking-grid' in l and '<div' in l and 'class=' in l:
            ranking_start = i
            break

print(f'buy-points region: lines {market_end+1} to {ranking_start}')

# Print what we're about to remove for debugging
for i in range(market_end, ranking_start):
    print(f'  DEL {i+1}: {lines[i].rstrip()[:100]}')

# Find where market-section's closing </div> and top-section closing </div> are
# We need to find the </div> that closes market-section, then the combine-card, then top-section closing

# Let's take a different approach - read the entire region and rebuild it
# First, find the exact boundaries of top-section
top_start = None
for i, l in enumerate(lines):
    if 'class="top-section"' in l:
        top_start = i
        break

print(f'top-section starts at line {top_start+1}')

# Find where market-section ends (its closing </div>)
# Read from market_end backwards to find the last-update div
last_update_line = None
auction_hint_end = None
for i in range(market_end, max(market_end - 20, 0), -1):
    if 'auction-hint' in lines[i] and 'display:none' in lines[i]:
        # Find the closing of auction-hint and market-section
        for j in range(i, i + 10):
            if lines[j].strip() == '</div>':
                auction_hint_end = j
                break
        break

# Find the closing </div> of market-section
# It should be after auction-hint closing
ms_close = None
for i in range(market_end - 1, market_end - 15, -1):
    if lines[i].strip() == '</div>' and i > 0:
        # Check if the next non-empty line is buy-points or combine
        for j in range(i + 1, min(i + 5, len(lines))):
            if lines[j].strip():
                if 'buy-points' in lines[j] or 'combine' in lines[j] or '<!--' in lines[j]:
                    ms_close = i
                break
        if ms_close:
            break

if ms_close is None:
    # Fallback: market-section closes right before buy-points comment
    ms_close = market_end - 1
    while ms_close > 0 and lines[ms_close].strip() == '':
        ms_close -= 1

print(f'market-section closes around line {ms_close+1}')

# ===== Step 2: Remove everything between market-section close and ranking-grid =====
# and replace with clean buy-points + combine-card

# Extract combine-card content (we need to preserve it)
combine_lines = []
in_combine = False
for i in range(market_end, ranking_start):
    l = lines[i]
    if 'combine-card' in l and '<div' in l:
        in_combine = True
    if in_combine:
        combine_lines.append(l)
        if l.strip() == '</div>' and in_combine:
            # Check depth
            depth = 0
            for cl in combine_lines:
                depth += cl.count('<div')
                depth -= cl.count('</div>')
            if depth <= 0:
                in_combine = False

print(f'Extracted combine-card: {len(combine_lines)} lines')
for cl in combine_lines:
    print(f'  COMBINE: {cl.rstrip()[:100]}')

# ===== Step 3: Build the new clean block =====
new_block = []
new_block.append('\n')
new_block.append('            <!-- 买点候选 -->\n')
new_block.append('            <div class="buy-points-panel" id="buy-points-panel" style="display:none;">\n')
new_block.append('                <h2>🎯 买点候选 <span id="buy-points-count" style="font-size:12px;color:#999;font-weight:normal;"></span></h2>\n')
new_block.append('                <div id="buy-points-market" class="buy-market-conditions"></div>\n')
new_block.append('                <div id="buy-points-list" class="buy-points-list"></div>\n')
new_block.append('            </div>\n')
new_block.append('\n')
# Re-add combine-card with proper indentation
for cl in combine_lines:
    new_block.append(cl)
new_block.append('\n')

# Replace the broken region
lines = lines[:market_end] + new_block + lines[ranking_start:]

print(f'Replaced lines {market_end+1}-{ranking_start} with {len(new_block)} lines')

# ===== Step 4: Fix CSS =====
content = ''.join(lines)

# Fix top-section grid to 3 columns
# Find current top-section CSS
top_css_patterns = [
    ('grid-template-columns: 1fr auto', 'grid-template-columns: 3fr 2fr 2fr'),
    ('grid-template-columns: 1fr 1fr', 'grid-template-columns: 3fr 2fr 2fr'),
    ('grid-template-columns: 2fr 1fr', 'grid-template-columns: 3fr 2fr 2fr'),
]

for old, new in top_css_patterns:
    if old in content:
        content = content.replace(old, new, 1)
        print(f'CSS: top-section grid changed: {old} -> {new}')
        break
else:
    print('WARNING: top-section grid pattern not found, searching...')
    # Find top-section CSS
    for i, l in enumerate(content.split('\n')):
        if '.top-section' in l and 'grid' in l:
            print(f'  Found: line {i+1}: {l.rstrip()[:120]}')

# Fix buy-points-panel CSS to match market-section
old_bp_css = '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); border-left: 3px solid #667eea; margin-bottom: 10px; }'
new_bp_css = '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }'

if old_bp_css in content:
    content = content.replace(old_bp_css, new_bp_css)
    print('CSS: buy-points-panel style unified (removed border-left, margin-bottom)')

# Add h2 style for buy-points to match market-section
old_bp_header = '.buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #333; }'
new_bp_header = '.buy-points-panel h2 { font-size: 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }\n        .buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #333; }'

if old_bp_header in content:
    content = content.replace(old_bp_header, new_bp_header)
    print('CSS: Added buy-points h2 style matching market-section')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

final_lines = content.split('\n')
print(f'\nDone. {len(final_lines)} lines')

# Verify
for i, l in enumerate(final_lines):
    if 'buy-points-panel' in l and '<div' in l:
        print(f'  buy-points div at line {i+1}')
    if 'combine-card' in l and '<div' in l and 'class=' in l:
        print(f'  combine-card div at line {i+1}')
    if 'ranking-grid' in l and '<div' in l:
        print(f'  ranking-grid div at line {i+1}')
    if 'top-section' in l and '<div' in l:
        print(f'  top-section div at line {i+1}')
