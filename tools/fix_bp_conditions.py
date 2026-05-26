import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    c = f.read()

changes = 0

# 1. Delete bond_net condition
marker1 = "id:'bond_net'"
if marker1 in c:
    # Find the full line(s) for bond_net entry
    start = c.find("{id:'bond_net'")
    # Go back to find leading whitespace
    line_start = c.rfind('\n', 0, start) + 1
    # Find the end: next condition starts with {id: or end of array
    end = c.find("{id:'bond_chg'", start)
    if end == -1:
        end = c.find('];', start)
    # Trim the bond_net block
    block = c[line_start:end]
    c = c[:line_start] + c[end:]
    changes += 1
    print('OK 1: Deleted bond_net condition')
else:
    print('SKIP 1: bond_net not found')

# 2. Add consecutive_attacks condition after in_top_ind
marker2 = "detail:function(r){return r.industry_name||'-';}},"
if marker2 in c:
    insert_after = c.find(marker2) + len(marker2)
    new_cond = """
            {id:'consec_attack', type:'stock', name:'\u8fde\u7eed\u4e0a\u653b>0', on:true,
             fn:function(r){return (parseInt(r.consecutive_attacks)||0)>0;},
             detail:function(r){return '\u8fde\u7eed'+(r.consecutive_attacks||0)+'\u6b21';}},"""
    c = c[:insert_after] + new_cond + c[insert_after:]
    changes += 1
    print('OK 2: Added consecutive_attacks condition')
else:
    print('SKIP 2: in_top_ind anchor not found')

# 3. Add star filter dropdown in header
old_h = """buy-points-count" style="font-size:12px;color:#999;font-weight:normal;"></span>
                    <span class="bp-settings-btn" onclick="toggleBpEditor()" title="""
if old_h in c:
    new_h = """buy-points-count" style="font-size:12px;color:#999;font-weight:normal;"></span>
                    <select id="bp-star-filter" onchange="runBuyPoints()" style="font-size:11px;padding:1px 4px;border:1px solid #ddd;border-radius:3px;margin-left:4px;"><option value="0">\u5168\u90e8</option><option value="1">\u2b50\u4ee5\u4e0a</option><option value="2">\u2b50\u2b50\u4ee5\u4e0a</option><option value="3">\u2b50\u2b50\u2b50\u5171\u632f</option></select>
                    <span class="bp-settings-btn" onclick="toggleBpEditor()" title="""
    c = c.replace(old_h, new_h)
    changes += 1
    print('OK 3: Added star filter dropdown')
else:
    print('SKIP 3: header not found')

# 4. Add star filter logic before rendering
old_r = "            // 4. \u6e32\u67d3\n            renderBpResult(mktConds, mktPass, candidates);"
if old_r in c:
    new_r = """            // 4. \u661f\u7ea7\u7b5b\u9009
            var minLevel = parseInt((document.getElementById('bp-star-filter')||{}).value) || 0;
            if (minLevel > 0) candidates = candidates.filter(function(x){ return x.level >= minLevel; });

            // 5. \u6e32\u67d3
            renderBpResult(mktConds, mktPass, candidates);"""
    c = c.replace(old_r, new_r)
    changes += 1
    print('OK 4: Added star filter logic')
else:
    print('SKIP 4: render anchor not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print(f'Done. {changes} changes applied.')
