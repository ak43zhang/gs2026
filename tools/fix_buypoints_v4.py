# fix_buypoints_v4.py — Replace buy-points with pure frontend engine
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

changes = 0

# ============================================================
# 1. Replace old bp-editor HTML (lines ~695-711)
# ============================================================
old_editor = '''                <div id="bp-editor" class="bp-editor" style="display:none;">
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">大盘条件</div>
                        <label><input type="checkbox" id="bp-body-gt-up" checked> 红柱数量 > 涨家数</label>
                        <label><input type="checkbox" id="bp-tick-ratio" checked> tick涨跌比 > <input type="number" id="bp-tick-ratio-val" value="1.0" step="0.1" min="0" style="width:50px"> </label>
                        <label><input type="checkbox" id="bp-strength"> 市场强度 > <input type="number" id="bp-strength-val" value="50" step="5" min="0" style="width:50px"> </label>
                    </div>
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">个股条件</div>
                        <label><input type="checkbox" id="bp-net-ratio" checked> 主力净额/峰值 > <input type="number" id="bp-net-ratio-val" value="0.9" step="0.1" min="0" max="1" style="width:50px"> </label>
                        <label><input type="checkbox" id="bp-industry" checked> 行业上攻排行前 <input type="number" id="bp-industry-val" value="10" step="1" min="1" style="width:50px"> 名</label>
                        <label><input type="checkbox" id="bp-change-pct"> 涨幅 > <input type="number" id="bp-change-pct-val" value="2" step="0.5" min="0" style="width:50px"> %</label>
                    </div>
                    <div class="bp-editor-actions">
                        <button onclick="saveBpConfig()">保存条件</button>
                        <button onclick="resetBpConfig()" class="bp-btn-secondary">重置默认</button>
                    </div>
                </div>'''

new_editor = '''                <div id="bp-editor" class="bp-editor" style="display:none;">
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">大盘条件</div>
                        <div id="bp-conds-market"></div>
                    </div>
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">个股条件</div>
                        <div id="bp-conds-stock"></div>
                    </div>
                    <div class="bp-editor-section">
                        <div class="bp-editor-title">联动条件</div>
                        <div id="bp-conds-link"></div>
                    </div>
                    <div class="bp-editor-actions">
                        <button onclick="saveBpConfig()">保存条件</button>
                        <button onclick="resetBpConfig()" class="bp-btn-secondary">重置默认</button>
                    </div>
                </div>'''

if old_editor in content:
    content = content.replace(old_editor, new_editor)
    changes += 1
    print('OK 1: Replaced bp-editor HTML')
else:
    print('SKIP 1: bp-editor HTML not found, trying flexible match...')
    # Try a more flexible approach
    m = re.search(r'<div id="bp-editor".*?</div>\s*</div>\s*</div>\s*</div>', content, re.DOTALL)
    if m:
        content = content[:m.start()] + new_editor + content[m.end():]
        changes += 1
        print('OK 1b: Replaced bp-editor HTML (flexible)')
    else:
        print('FAIL 1: Could not find bp-editor HTML')

# ============================================================
# 2. Cache market data after renderMarketData calls
# ============================================================
old_market = '''                if (r.success) {
                    renderMarketData('stock', r.data?.stock);
                    renderMarketData('bond', r.data?.bond);
                    syncTopHeight();'''
new_market = '''                if (r.success) {
                    _bpMktData = r.data || {};
                    renderMarketData('stock', r.data?.stock);
                    renderMarketData('bond', r.data?.bond);
                    syncTopHeight();
                    runBuyPoints();'''
if old_market in content:
    content = content.replace(old_market, new_market)
    changes += 1
    print('OK 2: Added market data caching + trigger')
else:
    print('SKIP 2: market callback not found')

# ============================================================
# 3. Cache stock ranking data after rendering
# ============================================================
# In loadStockRankingAtTime, after _rankRawData['stock-ranking'] = r.data
old_stock = "_rankRawData['stock-ranking'] = r.data;\n                    renderRanking('stock-ranking', r.data);"
new_stock = "_rankRawData['stock-ranking'] = r.data;\n                    _bpStockRank = r.data || [];\n                    renderRanking('stock-ranking', r.data);\n                    runBuyPoints();"
if old_stock in content:
    content = content.replace(old_stock, new_stock, 1)
    changes += 1
    print('OK 3a: Added stock ranking cache + trigger (first)')
else:
    print('SKIP 3a: stock ranking callback 1 not found')

# Second instance (loadStockRanking for filtered)
old_stock2 = "_rankRawData['stock-ranking'] = r.data;\n"
# Find all instances and add cache where not already done
# The filtered version should also cache
if "_bpStockRank = r.data" not in content.split("_rankRawData['stock-ranking'] = r.data;")[1] if "_rankRawData['stock-ranking'] = r.data;" in content else False:
    pass  # Already handled

# ============================================================
# 4. Cache bond ranking data  
# ============================================================
old_bond = "_rankRawData['bond-ranking'] = r.data;"
new_bond = "_rankRawData['bond-ranking'] = r.data;\n                    _bpBondRank = r.data || [];"
if old_bond in content:
    content = content.replace(old_bond, new_bond, 1)
    changes += 1
    print('OK 4: Added bond ranking cache')
else:
    print('SKIP 4: bond ranking callback not found')

# Add runBuyPoints after bond ranking renders
old_bond_render = "renderRanking('bond-ranking', filteredData);"
new_bond_render = "renderRanking('bond-ranking', filteredData);\n                    runBuyPoints();"
if old_bond_render in content:
    content = content.replace(old_bond_render, new_bond_render, 1)
    changes += 1
    print('OK 4b: Added trigger after bond ranking render')
else:
    print('SKIP 4b: bond render not found')

# ============================================================
# 5. Cache industry ranking data
# ============================================================
old_ind = "if(r.success) renderRanking('industry-ranking',r.data);"
new_ind = "if(r.success) { _bpIndRank = r.data || []; renderRanking('industry-ranking',r.data); runBuyPoints(); }"
if old_ind in content:
    content = content.replace(old_ind, new_ind)
    changes += 1
    print('OK 5: Added industry ranking cache + trigger')
else:
    print('SKIP 5: industry ranking callback not found')

# ============================================================
# 6. Remove old updateBuyPoints call from loadDataAtTime
# ============================================================
content = content.replace("            updateBuyPoints(timeStr);\n", "")
print('OK 6: Removed old updateBuyPoints calls from loadDataAtTime')
changes += 1

# ============================================================
# 7. Replace old buy-points JS block (lines ~2022-2149)
# ============================================================
new_bp_js = '''
        // ==================== 买点候选 v4 — 纯前端股债联合筛选 ====================
        var _bpMktData = null;
        var _bpStockRank = [];
        var _bpBondRank = [];
        var _bpIndRank = [];

        var BP_CONDITIONS = [
            // 大盘条件
            {id:'body_gt_cur', type:'market', name:'红柱>涨家数', on:true,
             fn:function(m){return (parseFloat(m.body_up)||0)>(parseFloat(m.cur_up)||0);},
             detail:function(m){return '红柱'+(m.body_up||0)+' vs 涨'+(m.cur_up||0);}},
            {id:'tick_ratio', type:'market', name:'tick比', on:true, param:'tick_min', def:1.0,
             fn:function(m,p){var d=parseFloat(m.min_down)||0; return d>0?(parseFloat(m.min_up)||0)/d>p:false;},
             detail:function(m,p){var d=parseFloat(m.min_down)||0; return 'tick比 '+(d>0?((parseFloat(m.min_up)||0)/d).toFixed(2):'0')+' > '+p;}},
            {id:'strength', type:'market', name:'强度', on:false, param:'str_min', def:50,
             fn:function(m,p){return (parseFloat(m.strength_score)||0)>p;},
             detail:function(m,p){return '强度 '+(m.strength_score||0)+' > '+p;}},
            // 个股条件
            {id:'net_ratio', type:'stock', name:'主力/峰值', on:true, param:'net_min', def:0.9,
             fn:function(r,p){var pk=parseFloat(r.max_cumulative_main_net)||0; return pk>0?(parseFloat(r.cumulative_main_net)||0)/pk>p:false;},
             detail:function(r){var pk=parseFloat(r.max_cumulative_main_net)||0; return pk>0?((parseFloat(r.cumulative_main_net)||0)/pk*100).toFixed(0)+'%':'N/A';}},
            {id:'change_pct', type:'stock', name:'涨幅%', on:false, param:'chg_min', def:2,
             fn:function(r,p){return parseFloat(r.change_pct||0)>p;},
             detail:function(r){return (parseFloat(r.change_pct||0)).toFixed(2)+'%';}},
            {id:'in_top_ind', type:'stock', name:'行业前N', on:true, param:'ind_top', def:10,
             fn:function(r,p,ctx){return ctx.topInd.has(r.industry_name);},
             detail:function(r){return r.industry_name||'-';}},
            // 联动条件
            {id:'bond_in_rank', type:'link', name:'债券在排行', on:true,
             fn:function(r,p,ctx){return r.bond_code&&r.bond_code!=='-'&&ctx.bondSet.has(r.bond_code);},
             detail:function(r,p,ctx){var b=ctx.bondMap[r.bond_code]; return b?'债'+r.bond_code:'无';}},
            {id:'bond_net', type:'link', name:'债券主力/峰值', on:false, param:'bnet_min', def:0.9,
             fn:function(r,p,ctx){var b=ctx.bondMap[r.bond_code]; if(!b)return false; var pk=parseFloat(b.max_cumulative_main_net)||0; return pk>0?(parseFloat(b.cumulative_main_net)||0)/pk>p:false;},
             detail:function(r,p,ctx){var b=ctx.bondMap[r.bond_code]; if(!b)return '-'; var pk=parseFloat(b.max_cumulative_main_net)||0; return pk>0?((parseFloat(b.cumulative_main_net)||0)/pk*100).toFixed(0)+'%':'N/A';}},
            {id:'bond_chg', type:'link', name:'债券涨幅', on:false, param:'bchg_min', def:2,
             fn:function(r,p,ctx){var b=ctx.bondMap[r.bond_code]; return b&&parseFloat(b.change_pct||0)>p;},
             detail:function(r,p,ctx){var b=ctx.bondMap[r.bond_code]; return b?(parseFloat(b.change_pct||0)).toFixed(2)+'%':'-';}}
        ];

        var _bpParams = {};

        function loadBpConfig() {
            try {
                var saved = localStorage.getItem('buyPointsConfig');
                if (saved) { _bpParams = JSON.parse(saved); return; }
            } catch(e) {}
            _bpParams = {};
            BP_CONDITIONS.forEach(function(c) {
                if (c.param) _bpParams[c.param] = c.def;
                _bpParams['_on_' + c.id] = c.on;
            });
        }

        function saveBpConfig() {
            // Read from editor checkboxes
            BP_CONDITIONS.forEach(function(c) {
                var cb = document.getElementById('bp-cb-' + c.id);
                if (cb) _bpParams['_on_' + c.id] = cb.checked;
                if (c.param) {
                    var inp = document.getElementById('bp-val-' + c.id);
                    if (inp) _bpParams[c.param] = parseFloat(inp.value) || c.def;
                }
            });
            localStorage.setItem('buyPointsConfig', JSON.stringify(_bpParams));
            var btn = document.querySelector('.bp-editor-actions button');
            if (btn) { btn.textContent = '✓ 已保存'; btn.style.background = '#4caf50'; setTimeout(function(){ btn.textContent='保存条件'; btn.style.background=''; }, 1500); }
            runBuyPoints();
        }

        function resetBpConfig() {
            _bpParams = {};
            BP_CONDITIONS.forEach(function(c) {
                if (c.param) _bpParams[c.param] = c.def;
                _bpParams['_on_' + c.id] = c.on;
            });
            localStorage.removeItem('buyPointsConfig');
            renderBpEditor();
            runBuyPoints();
        }

        function toggleBpEditor() {
            var el = document.getElementById('bp-editor');
            if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }

        function renderBpEditor() {
            var groups = {market: 'bp-conds-market', stock: 'bp-conds-stock', link: 'bp-conds-link'};
            for (var type in groups) {
                var container = document.getElementById(groups[type]);
                if (!container) continue;
                var html = '';
                BP_CONDITIONS.filter(function(c){return c.type===type;}).forEach(function(c) {
                    var checked = _bpParams['_on_' + c.id] ? 'checked' : '';
                    html += '<label><input type="checkbox" id="bp-cb-' + c.id + '" ' + checked + '> ' + c.name;
                    if (c.param) {
                        html += ' > <input type="number" id="bp-val-' + c.id + '" value="' + (_bpParams[c.param]||c.def) + '" step="0.1" style="width:50px">';
                    }
                    html += '</label>';
                });
                container.innerHTML = html;
            }
        }

        function runBuyPoints() {
            var panel = document.getElementById('buy-points-panel');
            if (!panel) return;
            panel.style.display = '';

            var mkt = (_bpMktData && _bpMktData.stock) ? _bpMktData.stock : {};

            // 1. 构建上下文 O(m+k)
            var bondSet = new Set();
            var bondMap = {};
            (_bpBondRank || []).forEach(function(b) { bondSet.add(b.code); bondMap[b.code] = b; });
            var indTop = parseInt(_bpParams.ind_top) || 10;
            var topInd = new Set((_bpIndRank || []).slice(0, indTop).map(function(i) { return i.name; }));
            var ctx = {bondSet: bondSet, bondMap: bondMap, topInd: topInd};

            // 2. 大盘条件
            var mktConds = [];
            var mktPass = 0;
            BP_CONDITIONS.filter(function(c){return c.type==='market' && _bpParams['_on_'+c.id];}).forEach(function(c) {
                var p = c.param ? (_bpParams[c.param]||c.def) : 0;
                var ok = false;
                try { ok = c.fn(mkt, p); } catch(e) {}
                mktConds.push({name: c.name, passed: ok, detail: c.detail ? c.detail(mkt, p) : ''});
                if (ok) mktPass++;
            });

            // 3. 逐股评估
            var stockConds = BP_CONDITIONS.filter(function(c){return (c.type==='stock'||c.type==='link') && _bpParams['_on_'+c.id];});
            var candidates = [];
            (_bpStockRank || []).forEach(function(row) {
                var score = 0, tags = [], hasLink = false;
                stockConds.forEach(function(c) {
                    var p = c.param ? (_bpParams[c.param]||c.def) : 0;
                    var ok = false;
                    try { ok = c.fn(row, p, ctx); } catch(e) {}
                    if (ok) { score++; tags.push(c.name); if(c.type==='link') hasLink=true; }
                });
                if (score > 0) {
                    var bond = bondMap[row.bond_code];
                    var level = hasLink ? (score >= 3 ? 3 : 2) : 1;
                    candidates.push({
                        code: row.code, name: row.name,
                        change_pct: row.change_pct,
                        bond_code: row.bond_code || '-', bond_name: row.bond_name || '-',
                        bond_chg: bond ? bond.change_pct : null,
                        score: score, tags: tags, level: level
                    });
                }
            });
            candidates.sort(function(a,b){return b.level-a.level||b.score-a.score;});
            candidates = candidates.slice(0, 30);

            // 4. 渲染
            renderBpResult(mktConds, mktPass, candidates);
            syncTopHeight();
        }

        function renderBpResult(mktConds, mktPass, candidates) {
            // 大盘条件
            var mktHtml = '';
            if (mktConds.length > 0) {
                var signal = mktPass >= mktConds.length ? '✅积极' : mktPass >= mktConds.length * 0.5 ? '⚠️谨慎' : '❌观望';
                mktHtml = '<span style="font-size:12px;">' + signal + ' (' + mktPass + '/' + mktConds.length + ')</span>';
                mktConds.forEach(function(c) {
                    mktHtml += '<div style="font-size:11px;color:' + (c.passed ? '#4caf50' : '#e57373') + ';">' + (c.passed ? '✓' : '✗') + ' ' + c.name + ' <span style="color:#999;">' + c.detail + '</span></div>';
                });
            }
            document.getElementById('buy-points-market').innerHTML = mktHtml;
            document.getElementById('buy-points-count').textContent = '(' + candidates.length + '只)';

            // 候选列表
            var el = document.getElementById('buy-points-list');
            if (candidates.length === 0) {
                el.innerHTML = '<div style="text-align:center;color:#bbb;padding:20px;font-size:12px;">当前无满足条件的候选</div>';
                return;
            }
            var stars = ['', '⭐', '⭐⭐', '⭐⭐⭐'];
            var html = '<table><thead><tr><th>等级</th><th>代码</th><th>名称</th><th>涨幅</th><th>关联债</th></tr></thead><tbody>';
            candidates.forEach(function(c) {
                var chg = c.change_pct !== null && c.change_pct !== '-' ? parseFloat(c.change_pct).toFixed(2) + '%' : '-';
                var chgColor = parseFloat(c.change_pct) > 0 ? '#e53935' : parseFloat(c.change_pct) < 0 ? '#43a047' : '#333';
                var bondInfo = '-';
                if (c.bond_code && c.bond_code !== '-') {
                    if (c.bond_chg !== null && c.bond_chg !== '-') {
                        bondInfo = c.bond_code + ' ' + parseFloat(c.bond_chg).toFixed(2) + '%';
                    } else {
                        bondInfo = c.bond_code;
                    }
                }
                html += '<tr><td>' + (stars[c.level]||'⭐') + '</td><td>' + c.code + '</td><td>' + c.name + '</td><td style="color:' + chgColor + ';">' + chg + '</td><td style="font-size:11px;color:#888;">' + bondInfo + '</td></tr>';
            });
            html += '</tbody></table>';
            el.innerHTML = html;
        }

        // Init
        loadBpConfig();
        renderBpEditor();
'''

# Find and replace old buy-points JS block
# It starts around "var _bpConfig = null;" and ends around "setTimeout(updateBuyPoints, 1500);"
old_start = '        var _bpConfig = null;'
old_end = "        setTimeout(updateBuyPoints, 1500);"

start_idx = content.find(old_start)
end_idx = content.find(old_end)
if start_idx != -1 and end_idx != -1:
    end_idx += len(old_end)
    content = content[:start_idx] + new_bp_js + content[end_idx:]
    changes += 1
    print('OK 7: Replaced old buy-points JS with v4 engine')
else:
    print(f'FAIL 7: Could not find old JS block (start={start_idx}, end={end_idx})')

# ============================================================
# 8. Remove old buy-points timer  
# ============================================================
old_timer = "        setInterval(function() { if (_isLive) updateBuyPoints(); }, 5000);\n"
content = content.replace(old_timer, '')
print('OK 8: Removed old updateBuyPoints timer')

# ============================================================
# 9. Remove old setTimeout for buy-points + syncTopHeight
# ============================================================
old_timeout = "        setTimeout(syncTopHeight, 2000);"
content = content.replace(old_timeout, '')
print('OK 9: Removed old syncTopHeight timeout')

# Write
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone. {changes} major changes applied.')
