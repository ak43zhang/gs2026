"""Add save_buy_points route to monitor.py"""

MONITOR_PATH = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

ROUTE_CODE = '''

# ==================== 【P2】买点候选保存路由 ====================
@monitor_bp.route('/buy-points/save', methods=['POST'])
@login_required
def save_buy_points():
    """保存买点候选（前端POST入口）"""
    try:
        data = request.get_json(silent=True) or {}
        date = data.get('date', '')
        time_str = data.get('time', '')
        candidates = data.get('candidates', [])
        market_context = data.get('market_context', {})
        
        if not date or not time_str:
            return jsonify(success=False, message='缺少日期或时间参数'), 400
        
        save_buy_point_candidates(date, time_str, candidates, market_context)
        return jsonify(success=True, message=f'已保存 {len(candidates)} 只')
    except Exception as e:
        print(f"[save_buy_points] {e}")
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

'''

with open(MONITOR_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if already exists
if 'def save_buy_points' in content:
    print('SKIP: save_buy_points already exists')
    exit(0)

# Find insertion point: after save_buy_point_candidates function, before # ==================== 【P1】
marker = '# ==================== 【P1】DataFrame 进程级内存缓存 ===================='
if marker not in content:
    print(f'FAIL: marker not found: {marker}')
    exit(1)

idx = content.index(marker)
content = content[:idx] + ROUTE_CODE + content[idx:]

with open(MONITOR_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'OK: inserted save_buy_points route ({len(ROUTE_CODE)} chars)')
print(f'New file size: {len(content)} chars')
