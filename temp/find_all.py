import glob

r = glob.glob('F:/pyworkspace2026/gs2026/**/monitor.html', recursive=True)
with open('F:/pyworkspace2026/gs2026/temp/paths2.txt', 'w') as f:
    f.write(f"count: {len(r)}\n")
    for p in r:
        with open(p, encoding='utf-8') as fh:
            c = fh.read()
        has_tab = 'bp-tab-btn' in c
        f.write(f"{p} | size={len(c)} | has_tab={has_tab}\n")
