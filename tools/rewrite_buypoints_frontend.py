# rewrite_buypoints_frontend.py - Complete frontend rewrite
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

# ===== 1. Replace HTML buy-points container =====
old_html_start = '            <!-- 买点候选 -->'
old_html_end = '            </div>'

# Find the buy-points panel in HTML
start = content.find(old_html_start)
if start == -1:
    print('ERROR: buy-points HTML not found')
    exit(1)

# Find its closing div (track depth)
lines = content[start:].split('\n')
depth = 0
end_offset = 0
for i, l in enumerate(lines):
    depth += l.count('<div')
    depth -= l.count('</div>')
    end_offset += len(l) + 1
    if depth <= 0 and i > 0:
        break

end = start + end_offset

print(f'Replacing HTML at chars {start}-{end}')

new_html = '''            <!-- 买点候选 -->
            <div class="buy-points-panel" id="buy-points-panel" style="display:none;">
                <h2>
                    🎯 买点候选 <span id="buy-points-count" style="font-size:12px;color:#999;font-weight:normal;"></span>
                    <span class="bp-settings-btn" onclick="toggleBpEditor()" title="条件设置">⚙</span>
                </h2>
                <div id="buy-points-market" class="buy-market-conditions"></div>
                <div id="buy-points-list" class="buy-points-list"></div>
                <!-- 条件编辑面板 -->
                <div id="bp-editor" class="bp-editor" style="display:none;">
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">大盘条件</div>
                        <label><input type="checkbox" id="bp-body-gt-up" checked> 红柱数量 > 涨家数</label>
                        <label><input type="checkbox" id="bp-tick-ratio" checked> tick涨跌比 > <input type="number" id="bp-tick-ratio-val" value="1.0" min="0" step="0.1" class="bp-input"></label>
                        <label><input type="checkbox" id="bp-strength"> 市场强度 > <input type="number" id="bp-strength-val" value="50" min="0" step="5" class="bp-input"></label>
                    </div>
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">个股条件</div>
                        <label><input type="checkbox" id="bp-net-ratio" checked> 主力净额/峰值 > <input type="number" id="bp-net-ratio-val" value="0.9" min="0" max="1" step="0.05" class="bp-input"></label>
                        <label><input type="checkbox" id="bp-industry" checked> 行业上攻排行前 <input type="number" id="bp-industry-val" value="10" min="1" max="30" class="bp-input"> 名</label>
                        <label><input type="checkbox" id="bp-change-pct"> 涨幅 > <input type="number" id="bp-change-pct-val" value="2" min="0" step="0.5" class="bp-input"> %</label>
                    </div>
                    <div class="bp-editor-actions">
                        <button onclick="saveBpConfig()">保存条件</button>
                        <button onclick="resetBpConfig()" class="bp-btn-secondary">重置默认</button>
                    </div>
                </div>
            </div>
'''

content = content[:start] + new_html + content[end:]

# ===== 2. Replace/Add CSS =====
# Find existing buy-points CSS and replace
old_css_marker = '        /* 买点候选面板 */'
css_end_marker = '        .buy-signal-bar'

css_start = content.find(old_css_marker)
if css_start == -1:
    print('WARNING: buy-points CSS marker not found')
else:
    css_end = content.find(css_end_marker, css_start)
    if css_end == -1:
        css_end = css_start + 500
    # Find end of buy-signal-bar line
    css_end = content.find('\n', css_end) + 1

    new_css = '''        /* 买点候选面板 */
        .buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
        .buy-points-panel h2 { font-size: 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
        .bp-settings-btn { cursor: pointer; font-size: 16px; color: #999; transition: color 0.2s; }
        .bp-settings-btn:hover { color: #667eea; }
        .buy-market-conditions { font-size: 12px; margin-bottom: 8px; line-height: 1.8; }
        .buy-market-conditions .cond-item { display: inline-block; margin-right: 12px; }
        .buy-market-conditions .cond-pass { color: #27ae60; }
        .buy-market-conditions .cond-fail { color: #e74c3c; }
        .buy-market-conditions .bp-signal { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; color: #fff; margin-left: 8px; }
        .buy-points-list { max-height: 200px; overflow-y: auto; }
        .buy-points-list table { width: 100%; font-size: 12px; border-collapse: collapse; }
        .buy-points-list th { color: #999; font-weight: 500; text-align: left; padding: 4px 6px; border-bottom: 1px solid #eee; position: sticky; top: 0; background: #fff; }
        .buy-points-list td { padding: 4px 6px; border-bottom: 1px solid #f5f5f5; }
        .bp-editor { margin-top: 10px; padding: 10px; background: #f8f9fb; border-radius: 6px; border: 1px solid #e8eaed; }
        .bp-editor-section { margin-bottom: 8px; }
        .bp-editor-title { font-size: 12px; font-weight: 600; color: #667eea; margin-bottom: 4px; }
        .bp-editor label { display: block; font-size: 12px; color: #555; padding: 2px 0; cursor: pointer; }
        .bp-editor label input[type="checkbox"] { margin-right: 4px; }
        .bp-input { width: 50px; padding: 2px 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 12px; text-align: center; }
        .bp-editor-actions { display: flex; gap: 8px; margin-top: 8px; }
        .bp-editor-actions button { padding: 4px 12px; border: none; border-radius: 4px; font-size: 12px; cursor: pointer; background: #667eea; color: #fff; }
        .bp-btn-secondary { background: #e0e0e0 !important; color: #555 !important; }
'''

    content = content[:css_start] + new_css + content[css_end:]
    print('CSS replaced')

# ===== 3. Replace JS updateBuyPoints =====
# Find and replace the entire buy-points JS block
js_marker_start = '        // ==================== 买点候选 ===================='
js_marker_end = "        setTimeout(updateBuyPoints, 1500);"

js_start = content.find(js_marker_start)
js_end = content.find(js_marker_end)

if js_start == -1 or js_end == -1:
    print('ERROR: buy-points JS markers not found')
    exit(1)

js_end += len(js_marker_end)

new_js = '''        // ==================== 买点候选 ====================
        var _bpConfig = null;
        var _bpEditorOpen = false;

        function getDefaultBpConfig() {
            return {
                body_gt_up: true, tick_ratio_min: 1.0, strength_min: 0,
                net_ratio_min: 0.9, industry_top: 10, change_pct_min: 0
            };
        }

        function loadBpConfig() {
            try {
                var saved = localStorage.getItem('buyPointsConfig');
                if (saved) { _bpConfig = JSON.parse(saved); return; }
            } catch(e) {}
            _bpConfig = getDefaultBpConfig();
        }

        function saveBpConfig() {
            _bpConfig = {
                body_gt_up: document.getElementById('bp-body-gt-up').checked,
                tick_ratio_min: document.getElementById('bp-tick-ratio').checked ? parseFloat(document.getElementById('bp-tick-ratio-val').value) || 1.0 : 0,
                strength_min: document.getElementById('bp-strength').checked ? parseFloat(document.getElementById('bp-strength-val').value) || 50 : 0,
                net_ratio_min: document.getElementById('bp-net-ratio').checked ? parseFloat(document.getElementById('bp-net-ratio-val').value) || 0.9 : 0,
                industry_top: document.getElementById('bp-industry').checked ? parseInt(document.getElementById('bp-industry-val').value) || 10 : 0,
                change_pct_min: document.getElementById('bp-change-pct').checked ? parseFloat(document.getElementById('bp-change-pct-val').value) || 2 : 0
            };
            localStorage.setItem('buyPointsConfig', JSON.stringify(_bpConfig));
            updateBuyPoints();
        }

        function resetBpConfig() {
            _bpConfig = getDefaultBpConfig();
            localStorage.removeItem('buyPointsConfig');
            syncEditorUI();
            updateBuyPoints();
        }

        function syncEditorUI() {
            if (!_bpConfig) return;
            document.getElementById('bp-body-gt-up').checked = _bpConfig.body_gt_up;
            document.getElementById('bp-tick-ratio').checked = _bpConfig.tick_ratio_min > 0;
            document.getElementById('bp-tick-ratio-val').value = _bpConfig.tick_ratio_min || 1.0;
            document.getElementById('bp-strength').checked = _bpConfig.strength_min > 0;
            document.getElementById('bp-strength-val').value = _bpConfig.strength_min || 50;
            document.getElementById('bp-net-ratio').checked = _bpConfig.net_ratio_min > 0;
            document.getElementById('bp-net-ratio-val').value = _bpConfig.net_ratio_min || 0.9;
            document.getElementById('bp-industry').checked = _bpConfig.industry_top > 0;
            document.getElementById('bp-industry-val').value = _bpConfig.industry_top || 10;
            document.getElementById('bp-change-pct').checked = _bpConfig.change_pct_min > 0;
            document.getElementById('bp-change-pct-val').value = _bpConfig.change_pct_min || 2;
        }

        function toggleBpEditor() {
            var el = document.getElementById('bp-editor');
            _bpEditorOpen = !_bpEditorOpen;
            el.style.display = _bpEditorOpen ? '' : 'none';
            if (_bpEditorOpen) syncEditorUI();
        }

        function updateBuyPoints(timeStr) {
            if (!_bpConfig) loadBpConfig();
            var url = buildUrl('/api/monitor/buy-points');
            var sep = url.includes('?') ? '&' : '?';
            url += sep + 'body_gt_up=' + _bpConfig.body_gt_up;
            url += '&tick_ratio_min=' + _bpConfig.tick_ratio_min;
            url += '&strength_min=' + _bpConfig.strength_min;
            url += '&net_ratio_min=' + _bpConfig.net_ratio_min;
            url += '&industry_top=' + _bpConfig.industry_top;
            url += '&change_pct_min=' + _bpConfig.change_pct_min;
            if (timeStr) url += '&time=' + timeStr;
            fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data || !data.success) return;
                var panel = document.getElementById('buy-points-panel');
                if (!panel) return;
                panel.style.display = '';

                // 大盘条件
                var mkt = data.market || {};
                var condHtml = '';
                (mkt.conditions || []).forEach(function(c) {
                    var icon = c.passed ? '✅' : '❌';
                    var cls = c.passed ? 'cond-pass' : 'cond-fail';
                    condHtml += '<span class="cond-item ' + cls + '">' + icon + ' ' + c.detail + '</span>';
                });
                var sigColor = mkt.signal === '积极' ? '#27ae60' : (mkt.signal === '谨慎' ? '#f39c12' : '#e74c3c');
                condHtml += '<span class="bp-signal" style="background:' + sigColor + '">' + (mkt.passed||0) + '/' + (mkt.total||0) + ' ' + (mkt.signal||'') + '</span>';
                document.getElementById('buy-points-market').innerHTML = condHtml;

                // 数量
                document.getElementById('buy-points-count').textContent = '(' + data.count + '只)';

                // 候选列表
                var list = data.candidates || [];
                var el = document.getElementById('buy-points-list');
                if (!list.length) {
                    el.innerHTML = '<div style="color:#999;text-align:center;padding:15px;font-size:12px;">当前无满足条件的候选</div>';
                    return;
                }
                var h = '<table><thead><tr><th>代码</th><th>名称</th><th>涨幅</th><th>主峰比</th><th>行业</th><th>条件</th></tr></thead><tbody>';
                list.forEach(function(s) {
                    var pct = (typeof s.change_pct === 'number') ? s.change_pct.toFixed(2) + '%' : '-';
                    var pc = (typeof s.change_pct === 'number' && s.change_pct > 0) ? '#e74c3c' : '#27ae60';
                    var rs = (s.net_ratio * 100).toFixed(0) + '%';
                    var rc = ratioToColor(s.net_ratio);
                    var icons = '';
                    if (s.cond_net_ratio) icons += '💰';
                    if (s.cond_industry) icons += '🏭';
                    if (s.cond_change_pct) icons += '📈';
                    h += '<tr><td style="color:#5dade2">' + s.code + '</td><td>' + s.name + '</td><td style="color:' + pc + '">' + pct + '</td><td style="color:' + rc + ';font-weight:600">' + rs + '</td><td style="color:#999">' + (s.industry_name||'-') + '</td><td>' + icons + '</td></tr>';
                });
                h += '</tbody></table>';
                el.innerHTML = h;
            }).catch(function(e) { console.error('buy-points error:', e); });
        }

        loadBpConfig();
        setInterval(function() { if (_isLive) updateBuyPoints(); }, 5000);
        setTimeout(updateBuyPoints, 1500);'''

content = content[:js_start] + new_js + content[js_end:]
print('JS replaced')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Done. File saved.')
