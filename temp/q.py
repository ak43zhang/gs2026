import sys
f=open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html',encoding='utf-8')
c=f.read()
f.close()
count = c.count('bp-tab-btn')
sys.stdout.write(str(count))
