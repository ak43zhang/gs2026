import sys
f=open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html',encoding='utf-8')
c=f.read()
f.close()
i=c.find('buy-points-panel')
chunk=c[i:i+500]
# Write each line numbered
with open(r'F:\pyworkspace2026\gs2026\temp\out.txt','w',encoding='utf-8') as o:
    for idx,line in enumerate(chunk.split('\n')[:12]):
        o.write(f"{idx}: {line}\n")
    o.write(f"\n---\nhas bp-tab-btn: {'bp-tab-btn' in c}\n")
    o.write(f"has switchBpTab: {'switchBpTab' in c}\n")
    o.write(f"has qs-tab-btn: {'qs-tab-btn' in c}\n")
