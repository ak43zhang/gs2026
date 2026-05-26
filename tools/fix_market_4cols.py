# fix_market_4cols.py — 大盘概览改为四列 + 调整三栏比例
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
with open(path, 'r', encoding='utf-8-sig') as f:
    c = f.read()

changes = 0

# 1. CSS: distribution-row 3列→4列
old = 'grid-template-columns: repeat(3, 1fr);\n            gap: 4px;\n            margin-bottom: 4px;\n        }\n        \n        /* 红绿柱区域 - 横向三列 */\n        .body-row {\n            display: grid;\n            grid-template-columns: 1fr 1fr 1.2fr;'
new = 'grid-template-columns: repeat(4, 1fr);\n            gap: 4px;\n            margin-bottom: 4px;\n        }\n        \n        /* 红绿柱区域 - 横向四列 */\n        .body-row {\n            display: grid;\n            grid-template-columns: repeat(4, 1fr);'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('OK 1: CSS grid 3→4 columns')
else:
    print('SKIP 1: CSS grid not found')

# 2. top-section 比例: 3fr 2fr 2fr → 4fr 2fr 1.5fr
old = 'grid-template-columns: 3fr 2fr 2fr;'
new = 'grid-template-columns: 4fr 2fr 1.5fr;'
if old in c:
    c = c.replace(old, new, 1)
    changes += 1
    print('OK 2: top-section columns 3:2:2 → 4:2:1.5')
else:
    print('SKIP 2: top-section columns not found')

# 3. renderMarketData — 涨跌分布加第4列(涨跌比)
old_dist = '''                distEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">🔴 上涨</div>
                        <div class="market-value ${uc}">${data.cur_up||0}</div>
                        <div class="market-sub">${ur.toFixed(1)}%</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">🟢 下跌</div>
                        <div class="market-value ${dc}">${data.cur_down||0}</div>
                        <div class="market-sub">${dr.toFixed(1)}%</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">⚪ 平盘</div>
                        <div class="market-value neutral">${data.cur_flat||0}</div>
                        <div class="market-sub">${(data.cur_flat_ratio||0).toFixed(1)}%</div>
                    </div>
                `;'''

new_dist = '''                const udRatio = (data.cur_down||0) > 0 ? ((data.cur_up||0) / (data.cur_down||0)).toFixed(2) : '-';
                const udColor = parseFloat(udRatio) > 1 ? '#e53935' : parseFloat(udRatio) < 1 ? '#43a047' : '#666';
                distEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">🔴 上涨</div>
                        <div class="market-value ${uc}">${data.cur_up||0}</div>
                        <div class="market-sub">${ur.toFixed(1)}%</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">🟢 下跌</div>
                        <div class="market-value ${dc}">${data.cur_down||0}</div>
                        <div class="market-sub">${dr.toFixed(1)}%</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">⚪ 平盘</div>
                        <div class="market-value neutral">${data.cur_flat||0}</div>
                        <div class="market-sub">${(data.cur_flat_ratio||0).toFixed(1)}%</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">涨跌比</div>
                        <div class="market-value" style="color:${udColor}">${udRatio}</div>
                    </div>
                `;'''

if old_dist in c:
    c = c.replace(old_dist, new_dist)
    changes += 1
    print('OK 3: distribution row +涨跌比')
else:
    print('SKIP 3: distribution row not found')

# 4. tick区域加第4列(tick平) — 已有tick涨/tick跌/tick比，改为tick涨/tick跌/tick平/tick比
old_tick = '''                tickEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">tick涨</div>
                        <div class="market-value up">${mu}</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">tick跌</div>
                        <div class="market-value down">${md}</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">tick比</div>
                        <div class="market-value" style="color:${mc}">${mr}</div>
                    </div>
                `;'''

new_tick = '''                const mf = data.min_flat || 0;
                tickEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">tick涨</div>
                        <div class="market-value up">${mu}</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">tick跌</div>
                        <div class="market-value down">${md}</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">tick平</div>
                        <div class="market-value neutral">${mf}</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">tick比</div>
                        <div class="market-value" style="color:${mc}">${mr}</div>
                    </div>
                `;'''

if old_tick in c:
    c = c.replace(old_tick, new_tick)
    changes += 1
    print('OK 4: tick row +tick平')
else:
    print('SKIP 4: tick row not found')

# 5. 红绿柱区域加"平柱"列 — 红柱/绿柱/红绿柱比 → 红柱/绿柱/平柱/红绿柱比
old_body = '''                bodyEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">红柱</div>
                        <div class="market-value up">${bodyUp}</div>
                        <div class="market-sub">实体涨</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">绿柱</div>
                        <div class="market-value down">${bodyDown}</div>
                        <div class="market-sub">实体跌</div>
                    </div>
                    <div class="market-item" style="background: ${bodyState === 'bull-strong' ? '#e8f5e9' : bodyState === 'bull-weak' ? '#f1f8e9' : bodyState === 'bear-weak' ? '#ffebee' : bodyState === 'bear-strong' ? '#fce4ec' : '#e3f2fd'};">
                        <div class="market-label">红绿柱比</div>
                        <div class="market-value ${bodyState.startsWith('bull') ? 'up' : bodyState.startsWith('bear') ? 'down' : 'neutral'}">${bodyRatio ? (bodyRatio/100).toFixed(2) : '-'}</div>
                        <div class="market-sub" style="font-size: 10px; color: ${bodyState.startsWith('bull') ? '#2e7d32' : bodyState.startsWith('bear') ? '#c62828' : '#1565c0'};">${bodyStateText}</div>
                    </div>
                `;'''

new_body = '''                const bodyFlat = data.body_flat || data.cur_flat || 0;
                bodyEl.innerHTML = `
                    <div class="market-item">
                        <div class="market-label">红柱</div>
                        <div class="market-value up">${bodyUp}</div>
                        <div class="market-sub">实体涨</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">绿柱</div>
                        <div class="market-value down">${bodyDown}</div>
                        <div class="market-sub">实体跌</div>
                    </div>
                    <div class="market-item">
                        <div class="market-label">平柱</div>
                        <div class="market-value neutral">${bodyFlat}</div>
                        <div class="market-sub">实体平</div>
                    </div>
                    <div class="market-item" style="background: ${bodyState === 'bull-strong' ? '#e8f5e9' : bodyState === 'bull-weak' ? '#f1f8e9' : bodyState === 'bear-weak' ? '#ffebee' : bodyState === 'bear-strong' ? '#fce4ec' : '#e3f2fd'};">
                        <div class="market-label">红绿柱比</div>
                        <div class="market-value ${bodyState.startsWith('bull') ? 'up' : bodyState.startsWith('bear') ? 'down' : 'neutral'}">${bodyRatio ? (bodyRatio/100).toFixed(2) : '-'}</div>
                        <div class="market-sub" style="font-size: 10px; color: ${bodyState.startsWith('bull') ? '#2e7d32' : bodyState.startsWith('bear') ? '#c62828' : '#1565c0'};">${bodyStateText}</div>
                    </div>
                `;'''

if old_body in c:
    c = c.replace(old_body, new_body)
    changes += 1
    print('OK 5: body row +平柱')
else:
    print('SKIP 5: body row not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print(f'\nDone. {changes} changes applied.')
