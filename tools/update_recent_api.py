"""Update get_recent_buy_points to return distinct stocks with hit count"""

MONITOR_PATH = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

NEW_CODE = '''

@monitor_bp.route('/buy-points/recent', methods=['GET'])
def get_recent_buy_points():
    """获取近期买点候选（去重：每只股票只取最新一条，附带命中次数）"""
    from sqlalchemy import text
    try:
        date = request.args.get('date', '')
        limit = int(request.args.get('limit', '3'))
        before = request.args.get('before', '')
        if limit > 10: limit = 10

        save_date = date if '-' in date else (f'{date[:4]}-{date[4:6]}-{date[6:8]}' if len(date) == 8 else '')
        if not save_date:
            now = datetime.now()
            save_date = f'{now.year}-{now.month:02d}-{now.day:02d}'

        engine = _get_shared_engine()

        with engine.connect() as conn:
            # 构建WHERE条件
            where_clause = "date = :d"
            params = {'d': save_date, 'l': limit}
            if before:
                where_clause += " AND time <= :before"
                params['before'] = before

            # 查询：每只股票最新一条 + 命中次数
            sql = f"""
                WITH latest AS (
                    SELECT stock_code, stock_name, stock_price, stock_change_pct,
                           bond_code, bond_name, bond_price, bond_change_pct,
                           level, time, condition_count, total_conditions, conditions,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY time DESC) as rn
                    FROM buy_point_candidates
                    WHERE {where_clause}
                ),
                counts AS (
                    SELECT stock_code, COUNT(*) as hit_count
                    FROM buy_point_candidates
                    WHERE {where_clause}
                    GROUP BY stock_code
                )
                SELECT l.*, c.hit_count
                FROM latest l
                JOIN counts c ON l.stock_code = c.stock_code
                WHERE l.rn = 1
                ORDER BY l.time DESC
                LIMIT :l
            """

            result = conn.execute(text(sql), params)
            rows = result.fetchall()

            if not rows:
                return jsonify(success=True, items=[])

            # 组装返回数据
            items = []
            for row in rows:
                items.append({
                    'stock_code': row[0],
                    'stock_name': row[1],
                    'stock_price': float(row[2]) if row[2] else None,
                    'stock_change_pct': float(row[3]) if row[3] else 0,
                    'bond_code': row[4] or '',
                    'bond_name': row[5] or '',
                    'bond_price': float(row[6]) if row[6] else None,
                    'bond_change_pct': float(row[7]) if row[7] else 0,
                    'level': row[8] or 1,
                    'time': str(row[9]) if row[9] else '',
                    'condition_count': row[10] or 0,
                    'total_conditions': row[11] or 0,
                    'conditions': row[12] or '[]',
                    'hit_count': row[13] or 1
                })

            return jsonify(success=True, items=items)

    except Exception as e:
        print(f"[get_recent_buy_points] {e}")
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

'''

with open(MONITOR_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if already updated
if 'hit_count' in content and 'get_recent_buy_points' in content:
    # Check if it's the old version (with groups) or new version (with items)
    idx = content.find('def get_recent_buy_points')
    snippet = content[idx:idx+500] if idx > 0 else ''
    if 'items' in snippet and 'hit_count' in snippet:
        print('SKIP: already updated to new version')
        exit(0)

# Find and replace the old function
# Find the start of the function
start_marker = "@monitor_bp.route('/buy-points/recent'"
if start_marker not in content:
    print(f'FAIL: marker not found: {start_marker}')
    exit(1)

# Find the end of the function (next @monitor_bp.route or def at module level)
start_idx = content.find(start_marker)
end_idx = len(content)

# Look for next route or function definition at module level
lines = content[start_idx:].split('\n')
for i, line in enumerate(lines[1:], 1):
    if line.startswith('@monitor_bp.route') or (line.startswith('def ') and not line.startswith('def _')):
        end_idx = start_idx + sum(len(l) + 1 for l in lines[:i])
        break

# Replace
new_content = content[:start_idx] + NEW_CODE + content[end_idx:]

with open(MONITOR_PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'OK: updated get_recent_buy_points ({len(new_content) - len(content)} chars change)')
