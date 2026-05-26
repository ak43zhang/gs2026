import sys; sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. POST保存代码
print('✅ 前端POST' if '/api/monitor/buy-points/save' in content else '❌ 前端POST未找到')

# 2. _lastBpSave
print('✅ _lastBpSave' if 'var _lastBpSave' in content else '❌ _lastBpSave未找到')

# 3. 位置验证
lines = content.split('\n')
slice_line = save_line = star_line = 0
for i, l in enumerate(lines, 1):
    if 'candidates.slice(0, 30)' in l:
        slice_line = i
    if '/api/monitor/buy-points/save' in l:
        save_line = i
    if 'bp-star-filter' in l and 'minLevel' in l:
        star_line = i
if slice_line < save_line < star_line:
    print(f'✅ POST位置正确: slice({slice_line}) < save({save_line}) < filter({star_line})')
else:
    print(f'❌ 位置异常: slice={slice_line}, save={save_line}, filter={star_line}')

# 4. 后端路由
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    py = f.read()
print('✅ 后端路由' if "'/buy-points/save'" in py and 'def save_buy_points' in py else '❌ 后端路由未找到')

# 5. save函数适配
has_level = "c.get('level')" in py
has_tags = "c.get('tags'" in py
print('✅ save适配' if has_level and has_tags else '❌ save适配异常')
