# implement_buypoints_v2.py - Complete buy-points v2 implementation
import re

html_path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
py_path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

# ========== Part 1: HTML changes ==========
with open(html_path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

lines = content.split('\n')
print(f'Original HTML: {len(lines)} lines')

# 1a. Find and extract buy-points-panel HTML block
bp_html_start = None
bp_html_end = None
for i, l in enumerate(lines):
    if '<!-- 买点候选 -->' in l:
        bp_html_start = i
    if bp_html_start is not None and l.strip() == '</div>' and i > bp_html_start + 3:
        # Check if this closes the buy-points-panel
        if '<div class="buy-points-panel"' in '\n'.join(lines[bp_html_start:i+1]):
            bp_html_end = i + 1
            break

if bp_html_start is None:
    print('ERROR: buy-points HTML not found')
    exit(1)

# Include trailing blank line
while bp_html_end < len(lines) and lines[bp_html_end].strip() == '':
    bp_html_end += 1

bp_html_block = lines[bp_html_start:bp_html_end]
print(f'Found buy-points HTML at lines {bp_html_start+1}-{bp_html_end}: {len(bp_html_block)} lines')

# Remove from current position
lines = lines[:bp_html_start] + lines[bp_html_end:]

# 1b. Find combine-card and insert buy-points BEFORE it
combine_idx = None
for i, l in enumerate(lines):
    if 'combine-card' in l and 'class=' in l:
        combine_idx = i
        break

if combine_idx is None:
    print('ERROR: combine-card not found')
    exit(1)

print(f'Inserting buy-points before combine-card at line {combine_idx+1}')
lines = lines[:combine_idx] + bp_html_block + lines[combine_idx:]

# 1c. Replace CSS styles (dark → white theme)
content = '\n'.join(lines)

# Old CSS
old_css_patterns = [
    ('.buy-points-panel { background: #1a1f2e; border-radius: 8px; border-left: 3px solid #d4a847; padding: 12px 16px; margin-top: 12px; }',
     '.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); border-left: 3px solid #667eea; margin-bottom: 10px; }'),
    ('.buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #d4a847; }',
     '.buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #333; }'),
    ('.buy-points-list table { width: 100%; font-size: 12px; border-collapse: collapse; color: #d0d8e0; }',
     '.buy-points-list table { width: 100%; font-size: 12px; border-collapse: collapse; color: #333; }'),
    ('.buy-points-list th { color: #8899aa; font-weight: 500; text-align: left; padding: 4px 8px; border-bottom: 1px solid #2a3040; }',
     '.buy-points-list th { color: #999; font-weight: 500; text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee; }'),
    ('.buy-points-list td { padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }',
     '.buy-points-list td { padding: 4px 8px; border-bottom: 1px solid #f5f5f5; }'),
    ('.buy-market-conditions .cond-item { padding: 3px 0; color: #b0b8c8; }',
     '.buy-market-conditions .cond-item { padding: 3px 0; color: #666; }'),
]

for old, new in old_css_patterns:
    if old in content:
        content = content.replace(old, new)
        print(f'CSS replaced: {old[:50]}...')
    else:
        print(f'CSS not found: {old[:50]}...')

# 1d. Modify updateBuyPoints to support timeStr parameter
old_func = "function updateBuyPoints() {\n            fetch('/api/monitor/buy-points')"
new_func = "function updateBuyPoints(timeStr) {\n            var bpUrl = buildUrl('/api/monitor/buy-points');\n            if (timeStr) bpUrl += (bpUrl.includes('?') ? '&' : '?') + 'time=' + timeStr;\n            fetch(bpUrl)"

if old_func in content:
    content = content.replace(old_func, new_func)
    print('JS: updateBuyPoints now supports timeStr')
else:
    print('WARNING: updateBuyPoints function signature not found, trying alternate')
    # Try without the specific fetch line
    old_alt = "function updateBuyPoints() {"
    new_alt = "function updateBuyPoints(timeStr) {"
    if old_alt in content:
        content = content.replace(old_alt, new_alt, 1)
        # Also fix the fetch URL
        content = content.replace(
            "fetch('/api/monitor/buy-points')",
            "var bpUrl = buildUrl('/api/monitor/buy-points');\n            if (timeStr) bpUrl += (bpUrl.includes('?') ? '&' : '?') + 'time=' + timeStr;\n            fetch(bpUrl)",
            1
        )
        print('JS: updateBuyPoints fixed (alternate)')

# 1e. Add updateBuyPoints call to loadDataAtTime
old_load = "loadCombineSignal(timeStr);\n            updateLastUpdateTime();"
new_load = "loadCombineSignal(timeStr);\n            updateBuyPoints(timeStr);\n            updateLastUpdateTime();"

if old_load in content:
    content = content.replace(old_load, new_load)
    print('JS: Added updateBuyPoints to loadDataAtTime')
else:
    print('WARNING: loadDataAtTime pattern not found')

# 1f. Fix setInterval to only run in live mode
old_interval = "setInterval(updateBuyPoints, 5000);"
new_interval = "setInterval(function() { if (_isLive) updateBuyPoints(); }, 5000);"

if old_interval in content:
    content = content.replace(old_interval, new_interval)
    print('JS: setInterval now checks _isLive')
else:
    print('WARNING: setInterval pattern not found')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'HTML saved: {len(content.split(chr(10)))} lines')

# ========== Part 2: Backend route - add time support ==========
with open(py_path, 'r', encoding='utf-8') as f:
    py_content = f.read()

# Find the buy-points route and add time_str parameter
old_route = "date = request.args.get('date', datetime.now().strftime('%Y%m%d'))"
new_route = "date = request.args.get('date', datetime.now().strftime('%Y%m%d'))\n        time_str = request.args.get('time')"

if old_route in py_content:
    py_content = py_content.replace(old_route, new_route, 1)
    print('Python: Added time_str parameter')

# Update market stats call to pass time_str
old_stats = "market_data = data_service.get_market_stats(date=date, use_mysql=True)"
new_stats = "market_data = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)"

if old_stats in py_content:
    py_content = py_content.replace(old_stats, new_stats, 1)
    print('Python: get_market_stats now passes time_str')

with open(py_path, 'w', encoding='utf-8') as f:
    f.write(py_content)

print('Backend saved')

# ========== Verify ==========
print('\n=== Verification ===')
with open(html_path, 'r', encoding='utf-8-sig') as f:
    vc = f.read()

# Check buy-points position relative to combine-card
bp_pos = vc.find('buy-points-panel')
cc_pos = vc.find('combine-card')
rg_pos = vc.find('ranking-grid')
print(f'Position order: buy-points={bp_pos}, combine-card={cc_pos}, ranking-grid={rg_pos}')
if bp_pos < cc_pos < rg_pos:
    print('OK: buy-points is before combine-card')
else:
    print('WARNING: Position order may be wrong')

# Check timeStr support
if 'function updateBuyPoints(timeStr)' in vc:
    print('OK: updateBuyPoints supports timeStr')
if 'updateBuyPoints(timeStr)' in vc and 'loadCombineSignal' in vc:
    print('OK: loadDataAtTime calls updateBuyPoints')
if 'if (_isLive) updateBuyPoints()' in vc:
    print('OK: setInterval checks _isLive')
