"""
Dashboard2 - 个人中心路由

功能：
    - GET  /profile           → 个人中心页面
    - GET  /api/journal/get   → 获取指定日期的日志
    - POST /api/journal/save  → 保存/更新日志
    - GET  /api/journal/list  → 获取指定月份有日志的日期列表
    - POST /api/journal/delete → 删除指定日期的日志
"""

from flask import Blueprint, render_template, request, session, jsonify
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

profile_bp = Blueprint('profile', __name__)


def _get_engine():
    url = config_util.get_config('common.url')
    return create_engine(url)


def _current_user():
    return session.get('username')


@profile_bp.route('/profile')
def profile_page():
    return render_template('profile.html')


@profile_bp.route('/api/journal/get', methods=['GET'])
def journal_get():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    date = request.args.get('date', '')
    if not date:
        return jsonify(success=False, message='缺少 date 参数')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text(
                'SELECT journal_date, content, todo_items, remarks, tags, mood '
                'FROM user_journals WHERE username = :u AND journal_date = :d'
            ),
            {'u': username, 'd': date}
        )
        row = r.fetchone()

    if row:
        return jsonify(success=True, data={
            'journal_date': str(row[0]),
            'content': row[1] or '',
            'todo_items': row[2] or '',
            'remarks': row[3] or '',
            'tags': row[4] or '',
            'mood': row[5] or '',
        })
    else:
        return jsonify(success=True, data=None)


@profile_bp.route('/api/journal/save', methods=['POST'])
def journal_save():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    date = body.get('date', '')
    if not date:
        return jsonify(success=False, message='缺少 date')

    content = body.get('content', '')
    todo_items = body.get('todo_items', '')
    remarks = body.get('remarks', '')
    tags = body.get('tags', '')
    mood = body.get('mood', '')

    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(
            text('''
                INSERT INTO user_journals (username, journal_date, content, todo_items, remarks, tags, mood)
                VALUES (:u, :d, :content, :todo, :remarks, :tags, :mood)
                ON DUPLICATE KEY UPDATE
                    content = VALUES(content),
                    todo_items = VALUES(todo_items),
                    remarks = VALUES(remarks),
                    tags = VALUES(tags),
                    mood = VALUES(mood)
            '''),
            {
                'u': username, 'd': date,
                'content': content, 'todo': todo_items,
                'remarks': remarks, 'tags': tags, 'mood': mood
            }
        )
        conn.commit()

    return jsonify(success=True, message='保存成功')


@profile_bp.route('/api/journal/list', methods=['GET'])
def journal_list():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    year = request.args.get('year', '')
    month = request.args.get('month', '')

    if not year or not month:
        return jsonify(success=False, message='缺少 year/month')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text(
                'SELECT journal_date FROM user_journals '
                'WHERE username = :u AND YEAR(journal_date) = :y AND MONTH(journal_date) = :m '
                'ORDER BY journal_date'
            ),
            {'u': username, 'y': int(year), 'm': int(month)}
        )
        dates = [str(row[0]) for row in r.fetchall()]

    return jsonify(success=True, data=dates)


@profile_bp.route('/api/journal/delete', methods=['POST'])
def journal_delete():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    date = body.get('date', '')
    if not date:
        return jsonify(success=False, message='缺少 date')

    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text('DELETE FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': date}
        )
        conn.commit()

    if result.rowcount > 0:
        return jsonify(success=True, message='删除成功')
    else:
        return jsonify(success=False, message='该日期无日志')
