# fix_buypoints.py - Insert buy-points panel (HTML + CSS + JS)
import sys

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print(f'Original: {len(lines)} lines')

# ========== 1. Find HTML insertion point ==========
# After combine-card closing div, before ranking-grid comment
html_idx = None
for i, l in enumerate(lines):
    if '<!-- ' in l and '排行榜' in l:
        html_idx = i
        break

if html_idx is None:
    print('ERROR: cannot find ranking comment')
    sys.exit(1)

print(f'HTML insert before line {html_idx + 1}: {lines[html_idx].rstrip()[:80]}')

html_block = [
    '        <!-- 买点候选 -->\n',
    '        <div class="buy-points-panel" id="buy-points-panel" style="display:none;margin-bottom:12px;">\n',
    '            <div class="buy-points-header">\n',
    '                <span>🎯 买点候选</span>\n',
    '                <span id="buy-points-count" style="font-size:12px;color:#999;"></span>\n',
    '            </div>\n',
    '            <div class="buy-points-body">\n',
    '                <div id="buy-points-market" class="buy-market-conditions"></div>\n',
    '                <div id="buy-points-list" class="buy-points-list"></div>\n',
    '            </div>\n',
    '        </div>\n',
    '\n',
]

# ========== 2. Find CSS insertion point ==========
# After .score-row styles, before ranking styles
css_idx = None
for i, l in enumerate(lines):
    if '/* ===== 排行榜 =====' in l:
        css_idx = i
        break

if css_idx is None:
    print('ERROR: cannot find ranking CSS comment')
    sys.exit(1)

print(f'CSS insert before line {css_idx + 1}')

css_block = [
    '        /* 买点候选面板 */\n',
    '        .buy-points-panel { background: #1a1f2e; border-radius: 8px; border-left: 3px solid #d4a847; padding: 12px 16px; margin-top: 12px; }\n',
    '        .buy-points-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #d4a847; }\n',
    '        .buy-points-body { display: flex; gap: 16px; }\n',
    '        .buy-market-conditions { flex: 0 0 200px; font-size: 12px; }\n',
    '        .buy-market-conditions .cond-item { padding: 3px 0; color: #b0b8c8; }\n',
    '        .buy-market-conditions .cond-pass { color: #27ae60; }\n',
    '        .buy-market-conditions .cond-fail { color: #e74c3c; }\n',
    '        .buy-points-list { flex: 1; overflow-x: auto; }\n',
    '        .buy-points-list table { width: 100%; font-size: 12px; border-collapse: collapse; color: #d0d8e0; }\n',
    '        .buy-points-list th { color: #8899aa; font-weight: 500; text-align: left; padding: 4px 8px; border-bottom: 1px solid #2a3040; }\n',
    '        .buy-points-list td { padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }\n',
    '        .buy-signal-bar { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }\n',
    '\n',
]

# ========== 3. Find JS insertion point ==========
# Before the last </script> tag
js_idx = None
for i in range(len(lines) - 1, -1, -1):
    if '</script>' in lines[i]:
        js_idx = i
        break

if js_idx is None:
    print('ERROR: cannot find closing script tag')
    sys.exit(1)

print(f'JS insert before line {js_idx + 1}')

js_block = [
    '\n',
    '        // ==================== 买点候选 ====================\n',
    '        function updateBuyPoints() {\n',
    "            fetch('/api/monitor/buy-points')\n",
    '            .then(function(r) { return r.json(); })\n',
    '            .then(function(data) {\n',
    '                if (!data || !data.success) return;\n',
    "                var panel = document.getElementById('buy-points-panel');\n",
    '                if (!panel) return;\n',
    "                panel.style.display = '';\n",
    '                var mkt = data.market || {};\n',
    "                var condHtml = '';\n",
    '                (mkt.conditions || []).forEach(function(c) {\n',
    "                    var icon = c.passed ? '\\u2705' : '\\u274c';\n",
    "                    var cls = c.passed ? 'cond-pass' : 'cond-fail';\n",
    '                    condHtml += \'<div class="cond-item \' + cls + \'">\' + icon + \' \' + c.detail + \'</div>\';\n',
    '                });\n',
    "                var signalColor = mkt.signal === '\\u79ef\\u6781' ? '#27ae60' : (mkt.signal === '\\u8c28\\u614e' ? '#f39c12' : '#e74c3c');\n",
    '                condHtml += \'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #2a3040;">\';\n',
    "                condHtml += '<span style=\"color:#8899aa;\">\\u901a\\u8fc7 ' + mkt.passed + '/' + mkt.total + '</span> ';\n",
    '                condHtml += \'<span class="buy-signal-bar" style="background:\' + signalColor + \';color:#fff;">\' + mkt.signal + \'</span>\';\n',
    "                condHtml += '</div>';\n",
    "                document.getElementById('buy-points-market').innerHTML = condHtml;\n",
    "                document.getElementById('buy-points-count').textContent = '\\uff08' + data.count + '\\u53ea\\uff09';\n",
    '                var list = data.candidates || [];\n',
    '                if (!list.length) {\n',
    '                    document.getElementById(\'buy-points-list\').innerHTML = \'<div style="color:#666;text-align:center;padding:20px;">\\u5f53\\u524d\\u65e0\\u5019\\u9009</div>\';\n',
    '                    return;\n',
    '                }\n',
    "                var html = '<table><thead><tr><th>\\u4ee3\\u7801</th><th>\\u540d\\u79f0</th><th>\\u6da8\\u5e45</th><th>\\u4e3b\\u5cf0\\u6bd4</th><th>\\u884c\\u4e1a</th><th>\\u6761\\u4ef6</th></tr></thead><tbody>';\n",
    '                list.forEach(function(s) {\n',
    "                    var pct = (typeof s.change_pct === 'number') ? s.change_pct.toFixed(2) + '%' : '-';\n",
    "                    var pctColor = (typeof s.change_pct === 'number' && s.change_pct > 0) ? '#e74c3c' : '#27ae60';\n",
    "                    var ratioStr = (s.net_ratio * 100).toFixed(0) + '%';\n",
    '                    var ratioColor = ratioToColor(s.net_ratio);\n',
    "                    var condIcons = '';\n",
    "                    if (s.cond_net_ratio) condIcons += '<span title=\"\\u4e3b\\u5cf0\\u6bd4>0.9\" style=\"color:#27ae60;\">\\ud83d\\udcb0</span>';\n",
    "                    if (s.cond_industry) condIcons += '<span title=\"\\u884c\\u4e1a\\u524d10\" style=\"color:#f39c12;\">\\ud83c\\udfed</span>';\n",
    "                    html += '<tr>';\n",
    "                    html += '<td style=\"color:#5dade2;\">' + s.code + '</td>';\n",
    "                    html += '<td>' + s.name + '</td>';\n",
    "                    html += '<td style=\"color:' + pctColor + ';\">' + pct + '</td>';\n",
    "                    html += '<td style=\"color:' + ratioColor + ';font-weight:600;\">' + ratioStr + '</td>';\n",
    "                    html += '<td style=\"color:#8899aa;\">' + (s.industry_name || '-') + '</td>';\n",
    "                    html += '<td>' + condIcons + '</td>';\n",
    "                    html += '</tr>';\n",
    '                });\n',
    "                html += '</tbody></table>';\n",
    "                document.getElementById('buy-points-list').innerHTML = html;\n",
    "            }).catch(function(e) { console.error('buy-points error:', e); });\n",
    '        }\n',
    '        setInterval(updateBuyPoints, 5000);\n',
    '        setTimeout(updateBuyPoints, 1500);\n',
    '\n',
]

# ========== Apply insertions (bottom-up to preserve line numbers) ==========
# Sort insertion points from bottom to top
insertions = sorted([
    (js_idx, js_block, 'JS'),
    (html_idx, html_block, 'HTML'),
    (css_idx, css_block, 'CSS'),
], key=lambda x: -x[0])

for idx, block, label in insertions:
    lines = lines[:idx] + block + lines[idx:]
    print(f'{label}: inserted {len(block)} lines before original line {idx + 1}')

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Done. New file: {len(lines)} lines')
