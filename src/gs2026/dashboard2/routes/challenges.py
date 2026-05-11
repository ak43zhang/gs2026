"""
挑战系统路由

API:
    GET  /api/challenges/list           → 挑战列表
    GET  /api/challenges/detail/<id>    → 挑战详情+统计
    POST /api/challenges/create         → 创建挑战
    POST /api/challenges/update/<id>    → 更新挑战
    POST /api/challenges/delete/<id>    → 删除挑战
    POST /api/challenges/complete/<id>  → 完成挑战
    POST /api/challenge/checkin/<id>    → 打卡
    POST /api/challenge/uncheckin/<id>  → 取消打卡
    GET  /api/challenge/cal/<id>        → 月度打卡日历
"""
import json
from datetime import date as date_type, datetime, timedelta

from flask import Blueprint, request, session, jsonify
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

challenge_bp = Blueprint('challenge', __name__)


def _get_engine():
    url = config_util.get_config('common.url')
    url = url.replace('charset=utf8&', 'charset=utf8mb4&').replace('charset=utf8"', 'charset=utf8mb4"')
    if 'charset=' not in url:
        url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
    return create_engine(url)


def _current_user():
    return session.get('username')


def _calc_stats(conn, username, challenge_id, target_days, created_at):
    """计算挑战统计：打卡总数、当前连续、最长连续、进度"""
    r = conn.execute(text(
        'SELECT log_date FROM user_challenge_logs '
        'WHERE username = :u AND challenge_id = :cid AND is_deleted = 0 '
        'ORDER BY log_date'
    ), {'u': username, 'cid': challenge_id})
    dates = sorted([row[0] for row in r.fetchall()])

    total_checked = len(dates)
    today = date_type.today()
    today_checked = today in dates

    # 当前连续天数（从今天往前数）
    current_streak = 0
    d = today
    date_set = set(dates)
    while d in date_set:
        current_streak += 1
        d -= timedelta(days=1)

    # 最长连续天数
    longest_streak = 0
    streak = 0
    prev = None
    for dt in dates:
        if prev and (dt - prev).days == 1:
            streak += 1
        else:
            streak = 1
        longest_streak = max(longest_streak, streak)
        prev = dt

    progress_pct = min(100, int(total_checked * 100 / target_days)) if target_days > 0 else 0
    remaining = max(0, target_days - total_checked) if target_days > 0 else 0

    return {
        'total_checked': total_checked,
        'today_checked': today_checked,
        'current_streak': current_streak,
        'longest_streak': longest_streak,
        'progress_pct': progress_pct,
        'remaining_days': remaining,
    }


# ==================== 挑战管理 ====================

@challenge_bp.route('/api/challenges/list')
def challenges_list():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    status_filter = request.args.get('status')
    engine = _get_engine()
    with engine.connect() as conn:
        sql = 'SELECT * FROM user_challenges WHERE username = :u AND is_deleted = 0'
        params = {'u': username}
        if status_filter is not None and status_filter != '':
            sql += ' AND status = :s'
            params['s'] = int(status_filter)
        sql += ' ORDER BY status ASC, updated_at DESC'
        r = conn.execute(text(sql), params)
        cols = r.keys()
        rows = [dict(zip(cols, row)) for row in r.fetchall()]

        items = []
        for row in rows:
            stats = _calc_stats(conn, username, row['id'], row['target_days'], row['created_at'])
            item = {
                'id': row['id'],
                'name': row['name'],
                'target_days': row['target_days'],
                'description': row['description'] or '',
                'color': row['color'] or '#667eea',
                'icon': row['icon'] or '🎯',
                'status': row['status'],
                'created_at': str(row['created_at']),
                **stats
            }
            # 自动完成检测
            if row['status'] == 1 and row['target_days'] > 0 and stats['total_checked'] >= row['target_days']:
                conn.execute(text('UPDATE user_challenges SET status = 2 WHERE id = :id'), {'id': row['id']})
                conn.commit()
                item['status'] = 2
            items.append(item)

    return jsonify(success=True, data=items)


@challenge_bp.route('/api/challenges/detail/<int:cid>')
def challenges_detail(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT * FROM user_challenges WHERE id = :id AND username = :u AND is_deleted = 0'
        ), {'id': cid, 'u': username})
        cols = r.keys()
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='挑战不存在'), 404

        row = dict(zip(cols, row))
        stats = _calc_stats(conn, username, cid, row['target_days'], row['created_at'])
        item = {
            'id': row['id'],
            'name': row['name'],
            'target_days': row['target_days'],
            'description': row['description'] or '',
            'color': row['color'] or '#667eea',
            'icon': row['icon'] or '🎯',
            'status': row['status'],
            'created_at': str(row['created_at']),
            **stats
        }

    return jsonify(success=True, data=item)


@challenge_bp.route('/api/challenges/create', methods=['POST'])
def challenges_create():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify(success=False, message='名称不能为空'), 400

    target_days = int(body.get('target_days', 21))
    description = body.get('description', '')
    color = body.get('color', '#667eea')
    icon = body.get('icon', '🎯')

    engine = _get_engine()
    with engine.connect() as conn:
        try:
            conn.execute(text(
                'INSERT INTO user_challenges (username, name, target_days, description, color, icon) '
                'VALUES (:u, :name, :days, :desc, :color, :icon)'
            ), {'u': username, 'name': name, 'days': target_days, 'desc': description, 'color': color, 'icon': icon})
            conn.commit()
        except Exception as e:
            if 'Duplicate' in str(e):
                return jsonify(success=False, message='同名挑战已存在'), 400
            raise

    return jsonify(success=True, message='创建成功')


@challenge_bp.route('/api/challenges/update/<int:cid>', methods=['POST'])
def challenges_update(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    sets = []
    params = {'id': cid, 'u': username}

    for field in ('name', 'description', 'color', 'icon'):
        if field in body:
            sets.append(f'{field} = :{field}')
            params[field] = body[field]
    if 'target_days' in body:
        sets.append('target_days = :target_days')
        params['target_days'] = int(body['target_days'])
    if 'status' in body:
        sets.append('status = :status')
        params['status'] = int(body['status'])

    if not sets:
        return jsonify(success=False, message='无更新字段'), 400

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            f'UPDATE user_challenges SET {", ".join(sets)} '
            f'WHERE id = :id AND username = :u AND is_deleted = 0'
        ), params)
        conn.commit()

    return jsonify(success=True, message='更新成功')


@challenge_bp.route('/api/challenges/delete/<int:cid>', methods=['POST'])
def challenges_delete(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            'UPDATE user_challenges SET is_deleted = 1 WHERE id = :id AND username = :u'
        ), {'id': cid, 'u': username})
        conn.execute(text(
            'UPDATE user_challenge_logs SET is_deleted = 1 WHERE challenge_id = :id AND username = :u'
        ), {'id': cid, 'u': username})
        conn.commit()

    return jsonify(success=True, message='已删除')


@challenge_bp.route('/api/challenges/complete/<int:cid>', methods=['POST'])
def challenges_complete(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            'UPDATE user_challenges SET status = 2 WHERE id = :id AND username = :u AND is_deleted = 0'
        ), {'id': cid, 'u': username})
        conn.commit()

    return jsonify(success=True, message='已标记完成')


# ==================== 打卡 ====================

@challenge_bp.route('/api/challenge/checkin/<int:cid>', methods=['POST'])
def challenge_checkin(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    log_date = body.get('date', str(date_type.today()))
    notes = body.get('notes', '')

    engine = _get_engine()
    with engine.connect() as conn:
        # 验证挑战存在
        r = conn.execute(text(
            'SELECT id, target_days FROM user_challenges WHERE id = :id AND username = :u AND is_deleted = 0'
        ), {'id': cid, 'u': username})
        ch = r.fetchone()
        if not ch:
            return jsonify(success=False, message='挑战不存在'), 404

        # 幂等打卡
        try:
            conn.execute(text(
                'INSERT INTO user_challenge_logs (username, challenge_id, log_date, notes) '
                'VALUES (:u, :cid, :d, :notes) '
                'ON DUPLICATE KEY UPDATE notes = VALUES(notes), is_deleted = 0'
            ), {'u': username, 'cid': cid, 'd': log_date, 'notes': notes})
            conn.commit()
        except Exception as e:
            return jsonify(success=False, message=str(e)), 500

        stats = _calc_stats(conn, username, cid, ch[1], None)

        # 自动完成
        if ch[1] > 0 and stats['total_checked'] >= ch[1]:
            conn.execute(text('UPDATE user_challenges SET status = 2 WHERE id = :id'), {'id': cid})
            conn.commit()

    return jsonify(success=True, message='打卡成功', data=stats)


@challenge_bp.route('/api/challenge/uncheckin/<int:cid>', methods=['POST'])
def challenge_uncheckin(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    log_date = body.get('date', str(date_type.today()))

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(
            'DELETE FROM user_challenge_logs '
            'WHERE username = :u AND challenge_id = :cid AND log_date = :d'
        ), {'u': username, 'cid': cid, 'd': log_date})
        conn.commit()

    return jsonify(success=True, message='已取消打卡')


# ==================== 日历 ====================

@challenge_bp.route('/api/challenge/cal/<int:cid>')
def challenge_cal(cid):
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    month = request.args.get('month', '')
    if not month:
        month = date_type.today().strftime('%Y-%m')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(text(
            'SELECT log_date, notes FROM user_challenge_logs '
            'WHERE username = :u AND challenge_id = :cid AND is_deleted = 0 '
            'AND DATE_FORMAT(log_date, "%%Y-%%m") = :m '
            'ORDER BY log_date'
        ), {'u': username, 'cid': cid, 'm': month})
        logs = [{'date': str(row[0]), 'notes': row[1] or ''} for row in r.fetchall()]

    return jsonify(success=True, data=logs)
