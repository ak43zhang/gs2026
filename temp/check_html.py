with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html','r',encoding='utf-8') as f:
    lines=f.readlines()
print('total lines:', len(lines))
for i,l in enumerate(lines):
    if 'bp-tab-btn' in l:
        print(f'bp-tab-btn at line {i+1}')
    if 'buy-points-panel' in l:
        print(f'buy-points-panel at line {i+1}')
    if 'switchBpTab' in l and 'function' in l:
        print(f'switchBpTab func at line {i+1}')
    if 'quant-screen-section' in l:
        print(f'quant-screen-section at line {i+1}')
