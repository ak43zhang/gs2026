import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    c = f.read()

changes = 0

# 1. Find .container CSS and add flex layout
# Need to find the existing .container rule
old_container = '.container { max-width:'
if old_container in c:
    # Find the full rule
    pos = c.find(old_container)
    end = c.find('}', pos) + 1
    old_rule = c[pos:end]
    # Add flex properties
    new_rule = old_rule.rstrip('}').rstrip() + ' height: 100vh; display: flex; flex-direction: column; overflow: hidden; }'
    c = c.replace(old_rule, new_rule)
    changes += 1
    print(f'OK 1: container → flex column + 100vh')
else:
    # Try alternative
    pos = c.find('.container {')
    if pos != -1:
        end = c.find('}', pos) + 1
        old_rule = c[pos:end]
        new_rule = old_rule.rstrip('}').rstrip() + ' height: 100vh; display: flex; flex-direction: column; overflow: hidden; }'
        c = c.replace(old_rule, new_rule)
        changes += 1
        print(f'OK 1b: container → flex column + 100vh')
    else:
        print('SKIP 1: .container not found')

# 2. top-section: add flex-shrink: 0
old_top = 'align-items: start;'
if old_top in c:
    c = c.replace(old_top, 'align-items: start; flex-shrink: 0;', 1)
    changes += 1
    print('OK 2: top-section flex-shrink: 0')
else:
    print('SKIP 2: top-section align-items not found')

# 3. ranking-grid: add flex:1, min-height:0, overflow:hidden
old_rank = '.ranking-grid { display: grid; grid-template-columns: 3fr 2fr 1fr; gap: 8px; }'
if old_rank in c:
    new_rank = '.ranking-grid { display: grid; grid-template-columns: 3fr 2fr 1fr; gap: 8px; flex: 1; min-height: 0; overflow: hidden; }'
    c = c.replace(old_rank, new_rank)
    changes += 1
    print('OK 3: ranking-grid → flex:1 + min-height:0')
else:
    print('SKIP 3: ranking-grid not found')

# 4. ranking-card: add flex column
old_card = '.ranking-card { background: #fff; border-radius: 8px; padding: 8px 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);'
if old_card in c:
    new_card = old_card + ' display: flex; flex-direction: column; min-height: 0;'
    c = c.replace(old_card, new_card, 1)
    changes += 1
    print('OK 4: ranking-card → flex column')
else:
    # Try with existing flex
    old_card2 = '.ranking-card { background: #fff; border-radius: 8px; padding: 8px 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); display: flex; flex-direction: column; min-height: 0;'
    if old_card2 in c:
        print('OK 4: ranking-card already has flex (skip)')
    else:
        print('SKIP 4: ranking-card not found')

# 5. ranking-scroll: remove max-height, add flex:1
old_scroll = '.ranking-scroll { max-height: calc(100vh - 280px); min-height: 400px; overflow-y: auto; overflow-x: auto; }'
if old_scroll in c:
    new_scroll = '.ranking-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: auto; }'
    c = c.replace(old_scroll, new_scroll)
    changes += 1
    print('OK 5: ranking-scroll → flex:1, removed max-height')
else:
    # Try partial match
    if 'ranking-scroll' in c and 'max-height: calc(100vh' in c:
        c = c.replace('max-height: calc(100vh - 280px); min-height: 400px;', 'flex: 1; min-height: 0;')
        changes += 1
        print('OK 5b: ranking-scroll max-height replaced with flex:1')
    else:
        print('SKIP 5: ranking-scroll not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print(f'\nDone. {changes} changes applied.')
