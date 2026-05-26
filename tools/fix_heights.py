# fix_heights.py - Make top section compact, rankings taller
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    # 1. top-section gap
    ('.top-section { display: grid;', None),  # skip, handle grid-gap below

    # 2. market-section padding
    ('.market-section { background: #fff; border-radius: 8px; padding: 12px 16px;',
     '.market-section { background: #fff; border-radius: 8px; padding: 8px 12px;'),

    # 3. market-section h2
    ('.market-section h2 { font-size: 16px; margin-bottom: 8px;',
     '.market-section h2 { font-size: 14px; margin-bottom: 4px;'),

    # 4. distribution-row gap
    ('gap: 6px;\n            margin-bottom: 6px;\n        }',
     'gap: 4px;\n            margin-bottom: 4px;\n        }'),

    # 5. body-row margin
    ('.body-row { margin: 4px 0; padding: 4px 8px; }',
     '.body-row { margin: 2px 0; padding: 2px 8px; }'),

    # 6. score-row
    ('.score-row { margin: 4px 0; padding: 4px 8px; }',
     '.score-row { margin: 2px 0; padding: 2px 8px; }'),

    # 7. buy-points panel padding
    ('.buy-points-panel { background: #fff; border-radius: 8px; padding: 12px 16px;',
     '.buy-points-panel { background: #fff; border-radius: 8px; padding: 8px 12px;'),

    # 8. buy-points list height
    ('.buy-points-list { max-height: 150px;',
     '.buy-points-list { max-height: 120px;'),

    # 9. combine-card padding
    ('.combine-card { background: #fff; border-radius: 8px; padding: 12px 14px;',
     '.combine-card { background: #fff; border-radius: 8px; padding: 8px 12px;'),

    # 10. combine-list height
    ('.combine-list { overflow-y: auto; flex: 1; max-height: 220px; }',
     '.combine-list { overflow-y: auto; flex: 1; max-height: 180px; }'),

    # 11. ranking-scroll dynamic height
    ('.ranking-scroll { max-height: 480px; overflow-y: auto; overflow-x: auto; }',
     '.ranking-scroll { max-height: calc(100vh - 360px); min-height: 300px; overflow-y: auto; overflow-x: auto; }'),

    # 12. ranking-card padding
    ('.ranking-card { background: #fff; border-radius: 8px; padding: 10px 14px;',
     '.ranking-card { background: #fff; border-radius: 8px; padding: 8px 12px;'),
]

count = 0
for old, new in replacements:
    if new is None:
        continue
    if old in content:
        content = content.replace(old, new, 1)
        count += 1
        print(f'OK: {old[:50]}...')
    else:
        print(f'SKIP: {old[:50]}...')

print(f'\nApplied {count} replacements')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Done.')
