"""Insert generate_effects API into monitor.py"""
import os

MONITOR_PATH = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

NEW_CODE = r'''

def _time_to_seconds(t):
    """时间/timedelta转秒数"""
    if t is None:
        return 0
    if hasattr(t, 'total_seconds'):
        return int(t.total_seconds())
    s = str(t)
    parts = s.split(':')
    if len(parts) == 3:
        return int(parts[0])*3600 + int(parts[1])*60 + int(float(parts[2]))
    return 0

def _find_nearest_price(prices, signal_time, offset_min):
    """在sssj价格序列中找 signal_time + offset_min 最近的价格"""
    sig_sec = _time_to_seconds(signal_time)
    target_sec = sig_sec + offset_min * 60
    if 41400 < target_sec < 46800:
        target_sec = 46800 + (target_sec - 41400)
    best_price = None
    best_diff = 999999
    for ts, price in prices:
        diff = abs(ts - target_sec)
        if diff < best_diff and diff < 300:
            best_diff = diff
            best_price = price
    return best_price

def _find_close_price(prices):
    """取最后一条价格作为收盘价"""
    if not prices:
        return None
    return prices[-1][1]


@monitor_bp.route('/buy-points/generate-effects', methods=['POST'])
def generate_effects():
    """为指定日期的买点候选填充效果追踪数据"""
    from sqlalchemy import text
    try:
        data = request.get_json(silent=True) or {}
        target_date = data.get('date', '')
        if not target_date:
            return jsonify(success=False, message='缺少date参数'), 400

        save_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}" if len(target_date) == 8 and '-' not in target_date else target_date

        engine = _get_shared_engine()
        filled = 0
        skipped = 0
        details = []

        with engine.connect() as conn:
            candidates = conn.execute(text(
                "SELECT record_id, stock_code, stock_name, stock_price, time, level "
                "FROM buy_point_candidates WHERE date = :d ORDER BY time DESC"
            ), {'d': save_date}).fetchall()

            if not candidates:
                return jsonify(success=True, filled=0, skipped=0, details=[], stats={})

            codes = list(set(str(c[1]) for c in candidates))
            sssj_data = {}
            placeholders = ','.join(["'" + c + "'" for c in codes])
            rows = conn.execute(text(
                f"SELECT code, timestamp, price FROM sssj "
                f"WHERE date = :d AND code IN ({placeholders}) "
                f"ORDER BY code, timestamp"
            ), {'d': save_date}).fetchall()
            for row in rows:
                sssj_data.setdefault(str(row[0]), []).append(
                    (_time_to_seconds(row[1]), float(row[2]))
                )

            for c in candidates:
                record_id = c[0]
                code = str(c[1])
                name = c[2]
                signal_price = float(c[3]) if c[3] else None
                signal_time = c[4]
                level = c[5]

                if not signal_price or signal_price <= 0:
                    skipped += 1
                    continue

                prices = sssj_data.get(code, [])
                if not prices:
                    skipped += 1
                    continue

                p5 = _find_nearest_price(prices, signal_time, 5)
                p15 = _find_nearest_price(prices, signal_time, 15)
                p30 = _find_nearest_price(prices, signal_time, 30)
                pc = _find_close_price(prices)

                def pct(p):
                    if p and signal_price:
                        return round((p - signal_price) / signal_price * 100, 4)
                    return None

                c5, c15, c30, cc = pct(p5), pct(p15), pct(p30), pct(pc)

                conn.execute(text(
                    "UPDATE buy_point_candidates SET "
                    "after_5m_price=:p5, after_5m_change_pct=:c5, "
                    "after_15m_price=:p15, after_15m_change_pct=:c15, "
                    "after_30m_price=:p30, after_30m_change_pct=:c30, "
                    "after_close_price=:pc, after_close_change_pct=:cc "
                    "WHERE record_id=:rid"
                ), {'p5':p5,'c5':c5,'p15':p15,'c15':c15,
                    'p30':p30,'c30':c30,'pc':pc,'cc':cc,'rid':record_id})
                filled += 1

                details.append({
                    'time': str(signal_time), 'code': code, 'name': name,
                    'signal_price': signal_price, 'level': level,
                    'after_5m': c5, 'after_15m': c15,
                    'after_30m': c30, 'after_close': cc
                })

            conn.commit()

        stats = {}
        for period, key in [('5m','after_5m'), ('15m','after_15m'), ('30m','after_30m'), ('close','after_close')]:
            valid = [d[key] for d in details if d[key] is not None]
            stats[period] = {
                'total': len(valid),
                'success': sum(1 for v in valid if v > 0),
                'success_rate': round(sum(1 for v in valid if v > 0) / len(valid) * 100, 1) if valid else 0,
                'avg_return': round(sum(valid) / len(valid), 4) if valid else 0
            }

        return jsonify(success=True, filled=filled, skipped=skipped,
                       details=details, stats=stats)
    except Exception as e:
        print(f"[generate-effects] {e}")
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

'''

ANCHOR = "@monitor_bp.route('/buy-points/recent'"

with open(MONITOR_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

if 'generate-effects' in content:
    print('SKIP: generate-effects already exists')
elif ANCHOR not in content:
    print('FAIL: anchor not found')
else:
    idx = content.index(ANCHOR)
    content = content[:idx] + NEW_CODE + '\n' + content[idx:]
    with open(MONITOR_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'OK: inserted {len(NEW_CODE)} chars before {ANCHOR}')
