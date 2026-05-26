# fix_sync_height.py - Use JS to sync heights + CSS cleanup
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

# 1. Add height sync JS function before the buy-points section
sync_js = '''
        // ==================== 顶部三栏高度同步 ====================
        function syncTopHeight() {
            var ms = document.querySelector('.market-section');
            var bp = document.getElementById('buy-points-panel');
            var cc = document.querySelector('.combine-card');
            if (!ms) return;
            var h = ms.offsetHeight;
            if (bp) { bp.style.maxHeight = h + 'px'; bp.style.overflow = 'hidden'; }
            if (cc) { cc.style.maxHeight = h + 'px'; cc.style.overflow = 'hidden'; }
        }
        window.addEventListener('resize', syncTopHeight);

'''

# Insert before buy-points section
marker = '        // ==================== 买点候选 ===================='
if marker in content:
    content = content.replace(marker, sync_js + marker)
    print('JS: syncTopHeight added')
else:
    print('ERROR: marker not found')
    exit(1)

# 2. Call syncTopHeight after market data renders
# Add it after renderOverview(data) call
old_render = 'renderOverview(data);'
new_render = 'renderOverview(data);\n                syncTopHeight();'
if old_render in content:
    content = content.replace(old_render, new_render, 1)
    print('JS: syncTopHeight called after renderOverview')

# 3. Also call after page load
old_timeout = "setTimeout(updateBuyPoints, 1500);"
new_timeout = "setTimeout(updateBuyPoints, 1500);\n        setTimeout(syncTopHeight, 2000);"
if old_timeout in content:
    content = content.replace(old_timeout, new_timeout, 1)
    print('JS: syncTopHeight called on page load')

# 4. CSS: remove align-items:stretch, use start instead (JS handles height)
content = content.replace('align-items: stretch;', 'align-items: start;')
print('CSS: align-items back to start (JS handles sync)')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Done.')
