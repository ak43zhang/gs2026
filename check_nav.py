from pathlib import Path
c = Path('src/gs2026/dashboard2/templates/profile.html').read_text(encoding='utf-8')
# Find sidebar nav event listener
idx = c.find('sidebarItem.dataset.page')
if idx > 0:
    print(c[max(0,idx-100):idx+500])
    print('---')
# Find sidebarItem.addEventListener
idx2 = c.find('sidebarItem.addEventListener')
if idx2 >= 0:
    print(c[idx2:idx2+400])
else:
    idx2 = c.find('addEventListener')
    if idx2 >= 0:
        print("First addEventListener:", c[idx2-20:idx2+100])
