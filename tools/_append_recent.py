from pathlib import Path
import sys, subprocess

appendix = r"""
@monitor_bp.route('/buy-points/recent', methods=['GET'])
def get_recent_buy_points():
    try:
        date = request.args.get('date', '')
        limit = int(request.args.get('limit', '3'))
        if limit > 10: limit = 10
        save_date = date if '-' in date else (f'{date[:4]}-{date[4:6]}-{date[6:8]}' if len(date) == 8 else '')
        if not save_date:
            now = datetime.now()
            save_date = f'{now.year}-{now.month:02d}-{now.day:02d}'

        engine = _get_shared_engine()
        groups = []

        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT DISTINCT time FROM buy_point_candidates WHERE date = :d ORDER BY time DESC LIMIT :l"),
                {'d': save_date, 'l': limit}
            )
            times = [str(row[0]) for row in result]
            if not times:
                return jsonify(success=True, groups=[])

            ts = ','.join([f"'{t}'" for t in times])
            result = conn.execute(
                text(f"SELECT time,stock_code,stock_name,stock_price,stock_change_pct,bond_code,bond_price,bond_change_pct,level,condition_count,total_conditions,conditions FROM buy_point_candidates WHERE date = :d AND time IN ({ts}) ORDER BY time DESC, level DESC, stock_code"),
                {'d': save_date}
            )

            time_map = {}
            for row in result:
                t = str(row[0])
                if t not in time_map:
                    time_map[t] = []
                time_map[t].append({
                    'stock_code': row[1], 'stock_name': row[2],
                    'stock_price': float(row[3]) if row[3] else None,
                    'stock_change_pct': float(row[4]) if row[4] else None,
                    'bond_code': row[5] or '',
                    'bond_price': float(row[6]) if row[6] else None,
                    'bond_change_pct': float(row[7]) if row[7] else None,
                    'level': row[8], 'condition_count': row[9],
                    'total_conditions': row[10], 'conditions': row[11]
                })

            for t in times:
                if t in time_map:
                    groups.append({'time': t, 'items': time_map[t]})

        return jsonify(success=True, groups=groups)
    except Exception as e:
        print(f'[buy-points/recent] {e}')
        return jsonify(success=False, message=str(e)), 500
"""

target = r'F:/pyworkspace2026/gs2026/src/gs2026/dashboard2/routes/monitor.py'
path = Path(target)
content = path.read_text(encoding='utf-8')
extra = '' if content.endswith('\n\n') else '\n'
path.write_text(content.rstrip('\n') + extra + appendix, encoding='utf-8')
print('OK: recent route appended')
