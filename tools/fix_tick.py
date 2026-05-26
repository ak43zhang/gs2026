# fix_tick.py - Insert tick rendering code into renderMarketData
import sys

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

# Find the exact insertion point: after distribution closing, before body section
# Looking for line with "// 2." and "红绿柱"
insert_idx = None
for i, line in enumerate(lines):
    if '// 2.' in line and '\u7ea2\u7eff\u67f1' in line:
        insert_idx = i
        break

if insert_idx is None:
    print('ERROR: Could not find body section comment')
    sys.exit(1)

print(f'Found body comment at line {insert_idx + 1}')
print(f'Previous line: {repr(lines[insert_idx - 1][:80])}')

# Build the tick code block
tick_lines = [
    '\n',
    '            // 1.5 tick\u6da8\u8dcc\n',
    "            const tickId = type + '-tick';\n",
    '            const tickEl = document.getElementById(tickId);\n',
    '            if (tickEl) {\n',
    '                const mu = data.min_up || 0;\n',
    '                const md = data.min_down || 0;\n',
    "                const mr = md > 0 ? (mu / md * 100).toFixed(1) : '-';\n",
    "                const mc = (parseFloat(mr) >= 100) ? '#e74c3c' : (parseFloat(mr) >= 80 ? '#f39c12' : '#27ae60');\n",
    '                tickEl.innerHTML = `\n',
    '                    ' + '<' + 'div class="market-item">' + '\n',
    '                        ' + '<' + 'div class="market-label">tick\u6da8' + '<' + '/div>' + '\n',
    '                        ' + '<' + 'div class="market-value up">${mu}' + '<' + '/div>' + '\n',
    '                    ' + '<' + '/div>' + '\n',
    '                    ' + '<' + 'div class="market-item">' + '\n',
    '                        ' + '<' + 'div class="market-label">tick\u8dcc' + '<' + '/div>' + '\n',
    '                        ' + '<' + 'div class="market-value down">${md}' + '<' + '/div>' + '\n',
    '                    ' + '<' + '/div>' + '\n',
    '                    ' + '<' + 'div class="market-item">' + '\n',
    '                        ' + '<' + 'div class="market-label">tick\u6bd4' + '<' + '/div>' + '\n',
    '                        ' + '<' + 'div class="market-value" style="color:${mc}">${mr}' + '<' + '/div>' + '\n',
    '                    ' + '<' + '/div>' + '\n',
    '                `;\n',
    '            }\n',
    '            \n',
]

# Actually let me just build proper HTML strings
tick_block = []
tick_block.append('\n')
tick_block.append('            // 1.5 tick涨跌\n')
tick_block.append("            const tickId = type + '-tick';\n")
tick_block.append('            const tickEl = document.getElementById(tickId);\n')
tick_block.append('            if (tickEl) {\n')
tick_block.append('                const mu = data.min_up || 0;\n')
tick_block.append('                const md = data.min_down || 0;\n')
tick_block.append("                const mr = md > 0 ? (mu / md * 100).toFixed(1) : '-';\n")
tick_block.append("                const mc = (parseFloat(mr) >= 100) ? '#e74c3c' : (parseFloat(mr) >= 80 ? '#f39c12' : '#27ae60');\n")
tick_block.append('                tickEl.innerHTML = `\n')
tick_block.append('                    <div class="market-item">\n')
tick_block.append('                        <div class="market-label">tick涨</div>\n')
tick_block.append('                        <div class="market-value up">${mu}</div>\n')
tick_block.append('                    </div>\n')
tick_block.append('                    <div class="market-item">\n')
tick_block.append('                        <div class="market-label">tick跌</div>\n')
tick_block.append('                        <div class="market-value down">${md}</div>\n')
tick_block.append('                    </div>\n')
tick_block.append('                    <div class="market-item">\n')
tick_block.append('                        <div class="market-label">tick比</div>\n')
tick_block.append('                        <div class="market-value" style="color:${mc}">${mr}</div>\n')
tick_block.append('                    </div>\n')
tick_block.append('                `;\n')
tick_block.append('            }\n')
tick_block.append('            \n')

# Insert before the body comment line
new_lines = lines[:insert_idx] + tick_block + lines[insert_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'SUCCESS: Inserted {len(tick_block)} lines before line {insert_idx + 1}')
print(f'New file has {len(new_lines)} lines (was {len(lines)})')
