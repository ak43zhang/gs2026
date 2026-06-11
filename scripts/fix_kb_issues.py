"""Fix kb issues in profile.html"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Fix toolbar display conflict
old_toolbar = 'id="kb-toolbar" style="display:none;padding:8px 16px;border-bottom:1px solid #e8e8e8;background:#fff;display:flex;align-items:center;gap:8px;"'
new_toolbar = 'id="kb-toolbar" style="display:none;padding:8px 16px;border-bottom:1px solid #e8e8e8;background:#fff;align-items:center;gap:8px;"'
if old_toolbar in content:
    content = content.replace(old_toolbar, new_toolbar)
    changes += 1
    print('[1] Fixed toolbar display conflict')
else:
    print('[1] Toolbar marker not found')

# 2. Fix kbEsc function
old_esc = """function kbEsc(s) {
    if (!s) return '';
    return s.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"');
}"""
new_esc = """function kbEsc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}"""
if old_esc in content:
    content = content.replace(old_esc, new_esc)
    changes += 1
    print('[2] Fixed kbEsc function')
else:
    print('[2] kbEsc marker not found')

# 3. Add search button next to search input
old_search = '<input id="kb-search" placeholder="搜索标题或内容..." oninput="kbDebounceSearch()" style="width:100%;padding:5px 8px;border:1px solid #d9d9d9;border-radius:4px;font-size:12px;">'
new_search = '<div style="display:flex;gap:4px;"><input id="kb-search" placeholder="搜索标题或内容..." oninput="kbDebounceSearch()" onkeydown="if(event.key===\'Enter\')kbLoadEntries()" style="flex:1;padding:5px 8px;border:1px solid #d9d9d9;border-radius:4px;font-size:12px;"><button onclick="kbLoadEntries()" style="padding:3px 8px;border-radius:4px;border:1px solid #d9d9d9;background:#fff;cursor:pointer;font-size:12px;">🔍</button></div>'
if old_search in content:
    content = content.replace(old_search, new_search)
    changes += 1
    print('[3] Added search button')
else:
    print('[3] Search marker not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone: {changes} changes')
