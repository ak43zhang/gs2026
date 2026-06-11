"""Remove tick-up related code from monitor.html and monitor.py"""

# ===== Fix monitor.html =====
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', encoding='utf-8') as f:
    content = f.read()

# Remove JS tick-up lines
old_js = """                // 【新增】tick上涨标记
                const isTickUp = item.is_tick_up === true;
                const tickUpClass = isTickUp ? ' tick-up-row' : '';
                
                let highlightRowClass = redRowClass || greenRowClass || tickUpClass;"""

new_js = """                let highlightRowClass = redRowClass || greenRowClass;"""

if old_js in content:
    content = content.replace(old_js, new_js)
    print('[HTML] Removed tick-up JS')
else:
    print('[HTML] tick-up JS not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'w', encoding='utf-8') as f:
    f.write(content)

# ===== Fix monitor.py =====
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', encoding='utf-8') as f:
    content = f.read()

# 1. Remove _mark_stock_tick_up call
old_call = """        # 【新增】标记3秒时间区间内的实时上攻数据（tick上涨）

        data = _mark_stock_tick_up(data, actual_date)



        # 【修改】排序：仅按次数倒序，tick上涨通过背景色标记不再优先排序

        data.sort(key=lambda x: -x.get('count', 0))"""

new_call = """        # 排序：按次数倒序

        data.sort(key=lambda x: -x.get('count', 0))"""

if old_call in content:
    content = content.replace(old_call, new_call)
    print('[PY] Removed _mark_stock_tick_up call')
else:
    print('[PY] _mark_stock_tick_up call not found')

# 2. Remove bond is_tick_up line
old_bond = """            bond['is_tick_up'] = is_realtime  # 【新增】tick上涨标记，用于前端背景色"""
if old_bond in content:
    content = content.replace(old_bond, "")
    print('[PY] Removed bond is_tick_up')
else:
    print('[PY] bond is_tick_up not found')

# 3. Remove entire _mark_stock_tick_up function
func_start = "def _mark_stock_tick_up(stocks: list, date: str) -> list:"
func_end = "def _mark_and_sort_realtime_attacks(bonds: list, date: str, time_str: str = None) -> list:"

if func_start in content and func_end in content:
    idx_start = content.index(func_start)
    idx_end = content.index(func_end)
    # Remove from func_start to func_end (keep func_end)
    content = content[:idx_start] + content[idx_end:]
    print('[PY] Removed _mark_stock_tick_up function')
else:
    print('[PY] _mark_stock_tick_up function not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
