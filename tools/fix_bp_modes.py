import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    c = f.read()

changes = 0

# 1. Add mode field to each stock/link condition in BP_CONDITIONS
replacements = [
    # Stock conditions
    ("id:'net_ratio', type:'stock', name:", "id:'net_ratio', type:'stock', mode:'required', name:"),
    ("id:'change_pct', type:'stock', name:", "id:'change_pct', type:'stock', mode:'required', name:"),
    ("id:'in_top_ind', type:'stock', name:", "id:'in_top_ind', type:'stock', mode:'bonus', name:"),
    ("id:'consec_attack', type:'stock', name:", "id:'consec_attack', type:'stock', mode:'required', name:"),
    # Link conditions
    ("id:'bond_in_rank', type:'link', name:", "id:'bond_in_rank', type:'link', mode:'bonus', name:"),
    ("id:'bond_chg', type:'link', name:", "id:'bond_chg', type:'link', mode:'bonus', name:"),
]

for old, new in replacements:
    if old in c and new not in c:
        c = c.replace(old, new)
        changes += 1

print(f'OK 1: Added mode to {changes} conditions')

# 2. Replace runBuyPoints evaluation logic
old_eval = """            // 3. \u9010\u80a1\u8bc4\u4f30
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
                if (score === stockConds.length && stockConds.length > 0) {
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
            });"""

new_eval = """            // 3. \u9010\u80a1\u8bc4\u4f30\uff08\u5fc5\u8981+\u52a0\u5206\u5206\u7ea7\uff09
            var stockConds = BP_CONDITIONS.filter(function(c){return (c.type==='stock'||c.type==='link') && _bpParams['_on_'+c.id];});
            var requiredConds = stockConds.filter(function(c){ var m = _bpParams['_mode_'+c.id] || c.mode || 'required'; return m === 'required'; });
            var bonusConds = stockConds.filter(function(c){ var m = _bpParams['_mode_'+c.id] || c.mode || 'required'; return m === 'bonus'; });
            var candidates = [];
            (_bpStockRank || []).forEach(function(row) {
                // \u5fc5\u8981\u6761\u4ef6\uff1a\u5168\u90e8\u901a\u8fc7\u624d\u5165\u9009
                var passAll = true, tags = [];
                requiredConds.forEach(function(c) {
                    var p = c.param ? (_bpParams[c.param]||c.def) : 0;
                    var ok = false;
                    try { ok = c.fn(row, p, ctx); } catch(e) {}
                    if (!ok) passAll = false;
                    else tags.push(c.name);
                });
                if (!passAll || requiredConds.length === 0 && bonusConds.length === 0) return;

                // \u52a0\u5206\u6761\u4ef6\uff1a\u7edf\u8ba1\u547d\u4e2d\u6570 \u2192 \u51b3\u5b9a\u661f\u7ea7
                var bonusHit = 0;
                bonusConds.forEach(function(c) {
                    var p = c.param ? (_bpParams[c.param]||c.def) : 0;
                    var ok = false;
                    try { ok = c.fn(row, p, ctx); } catch(e) {}
                    if (ok) { bonusHit++; tags.push(c.name); }
                });

                var level = 1 + Math.min(bonusHit, 2); // 1-3\u661f
                var bond = bondMap[row.bond_code];
                candidates.push({
                    code: row.code, name: row.name,
                    change_pct: row.change_pct,
                    bond_code: row.bond_code || '-', bond_name: row.bond_name || '-',
                    bond_chg: bond ? bond.change_pct : null,
                    score: requiredConds.length + bonusHit, tags: tags, level: level
                });
            });"""

if old_eval in c:
    c = c.replace(old_eval, new_eval)
    changes += 1
    print('OK 2: Replaced evaluation logic with required+bonus')
else:
    print('SKIP 2: old evaluation block not found')

# 3. Update renderBpEditor to add mode dropdown
old_editor = """                BP_CONDITIONS.filter(function(c){return c.type===type;}).forEach(function(c) {
                    var checked = _bpParams['_on_' + c.id] ? 'checked' : '';
                    html += '<label><input type="checkbox" id="bp-cb-' + c.id + '" ' + checked + '> ' + c.name;
                    if (c.param) {
                        html += ' > <input type="number" id="bp-val-' + c.id + '" value="' + (_bpParams[c.param]||c.def) + '" step="0.1" style="width:50px">';
                    }
                    html += '</label>';
                });"""

new_editor = """                BP_CONDITIONS.filter(function(c){return c.type===type;}).forEach(function(c) {
                    var checked = _bpParams['_on_' + c.id] ? 'checked' : '';
                    var curMode = _bpParams['_mode_' + c.id] || c.mode || 'required';
                    html += '<label style="display:flex;align-items:center;gap:4px;"><input type="checkbox" id="bp-cb-' + c.id + '" ' + checked + '> ' + c.name;
                    if (c.param) {
                        html += ' > <input type="number" id="bp-val-' + c.id + '" value="' + (_bpParams[c.param]||c.def) + '" step="0.1" style="width:50px">';
                    }
                    if (c.type !== 'market') {
                        html += ' <select id="bp-mode-' + c.id + '" style="font-size:11px;padding:1px 2px;border:1px solid #ddd;border-radius:3px;">';
                        html += '<option value="required"' + (curMode==='required'?' selected':'') + '>\u5fc5\u8981</option>';
                        html += '<option value="bonus"' + (curMode==='bonus'?' selected':'') + '>\u52a0\u5206</option></select>';
                    }
                    html += '</label>';
                });"""

if old_editor in c:
    c = c.replace(old_editor, new_editor)
    changes += 1
    print('OK 3: Updated editor with mode dropdown')
else:
    print('SKIP 3: old editor block not found')

# 4. Update saveBpConfig to save mode
old_save = """            BP_CONDITIONS.forEach(function(c) {
                var cb = document.getElementById('bp-cb-' + c.id);
                if (cb) _bpParams['_on_' + c.id] = cb.checked;
                if (c.param) {
                    var inp = document.getElementById('bp-val-' + c.id);
                    if (inp) _bpParams[c.param] = parseFloat(inp.value) || c.def;
                }
            });"""

new_save = """            BP_CONDITIONS.forEach(function(c) {
                var cb = document.getElementById('bp-cb-' + c.id);
                if (cb) _bpParams['_on_' + c.id] = cb.checked;
                if (c.param) {
                    var inp = document.getElementById('bp-val-' + c.id);
                    if (inp) _bpParams[c.param] = parseFloat(inp.value) || c.def;
                }
                var modeEl = document.getElementById('bp-mode-' + c.id);
                if (modeEl) _bpParams['_mode_' + c.id] = modeEl.value;
            });"""

if old_save in c:
    c = c.replace(old_save, new_save)
    changes += 1
    print('OK 4: Updated saveBpConfig to save mode')
else:
    print('SKIP 4: old save block not found')

# 5. Update resetBpConfig to reset mode
old_reset_line = "                _bpParams['_on_' + c.id] = c.on;"
new_reset_line = "                _bpParams['_on_' + c.id] = c.on;\n                if (c.mode) _bpParams['_mode_' + c.id] = c.mode;"
if old_reset_line in c:
    c = c.replace(old_reset_line, new_reset_line, 1)
    changes += 1
    print('OK 5: Updated resetBpConfig to reset mode')
else:
    print('SKIP 5: reset line not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print(f'\nDone. {changes} total changes.')
