"""
Dashboard2 - 个人中心路由

功能：
    - GET  /profile           → 个人中心页面
    - GET  /api/journal/get   → 获取指定日期的日志
    - POST /api/journal/save  → 保存/更新日志
    - GET  /api/journal/list  → 获取指定月份有日志的日期列表
    - POST /api/journal/delete → 删除指定日期的日志
    - GET  /api/todo/list     → 聚合所有日志的待办事项
    - POST /api/todo/toggle   → 切换待办完成状态
    - POST /api/todo/update   → 更新待办事项（文本/优先级）
    - POST /api/todo/delete   → 删除待办事项
    - GET  /api/todo/stats    → 待办统计
"""

import json
from datetime import date as date_type

from flask import Blueprint, render_template, request, session, jsonify
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

profile_bp = Blueprint('profile', __name__)


def _get_engine():
    url = config_util.get_config('common.url')
    # 替换 charset=utf8 为 utf8mb4 以支持 emoji（如心情字段）
    url = url.replace('charset=utf8&', 'charset=utf8mb4&').replace('charset=utf8"', 'charset=utf8mb4"')
    if 'charset=' not in url:
        url += ('&' if '?' in url else '?') + 'charset=utf8mb4'
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


# ============================================================
# 待办事项 API（聚合日志中的 todo_items）
# ============================================================

def _parse_todo_items(raw):
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if isinstance(items, list):
            result = []
            for item in items:
                if isinstance(item, dict):
                    if 'priority' not in item:
                        item['priority'] = 2
                    result.append(item)
                elif isinstance(item, str):
                    result.append({'text': item, 'done': False, 'priority': 2})
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    return []


@profile_bp.route('/api/todo/list', methods=['GET'])
def todo_list():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    sort_by = request.args.get('sort', 'date')
    filter_done = request.args.get('done', '0')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT journal_date, todo_items FROM user_journals '
                 'WHERE username = :u ORDER BY journal_date'),
            {'u': username}
        )
        rows = r.fetchall()

    today_str = str(date_type.today())
    todos = []
    for row in rows:
        journal_date = str(row[0])
        items = _parse_todo_items(row[1])
        for idx, item in enumerate(items):
            item_done = item.get('done', False)
            if filter_done == '0' and item_done:
                continue
            if filter_done == '1' and not item_done:
                continue
            todos.append({
                'date': journal_date,
                'index': idx,
                'text': item.get('text', ''),
                'done': item_done,
                'priority': item.get('priority', 2),
                'overdue': journal_date < today_str and not item_done,
            })

    if sort_by == 'priority':
        todos.sort(key=lambda x: (x['priority'], x['date']))
    else:
        todos.sort(key=lambda x: (x['date'], x['priority']))

    return jsonify(success=True, data=todos)


@profile_bp.route('/api/todo/toggle', methods=['POST'])
def todo_toggle():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')
    if not journal_date or index is None:
        return jsonify(success=False, message='缺少 date 或 index')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals '
                 'WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        items[index]['done'] = not items[index].get('done', False)
        conn.execute(
            text('UPDATE user_journals SET todo_items = :t '
                 'WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False),
             'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='切换成功')


@profile_bp.route('/api/todo/update', methods=['POST'])
def todo_update():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')
    if not journal_date or index is None:
        return jsonify(success=False, message='缺少 date 或 index')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals '
                 'WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        if 'text' in body:
            items[index]['text'] = body['text']
        if 'priority' in body:
            items[index]['priority'] = int(body['priority'])
        if 'done' in body:
            items[index]['done'] = bool(body['done'])

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t '
                 'WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False),
             'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='更新成功')


@profile_bp.route('/api/todo/delete', methods=['POST'])
def todo_delete_item():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')
    if not journal_date or index is None:
        return jsonify(success=False, message='缺少 date 或 index')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals '
                 'WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        items.pop(index)
        conn.execute(
            text('UPDATE user_journals SET todo_items = :t '
                 'WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False),
             'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='删除成功')


@profile_bp.route('/api/todo/stats', methods=['GET'])
def todo_stats():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    today_str = str(date_type.today())
    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT journal_date, todo_items FROM user_journals '
                 'WHERE username = :u'),
            {'u': username}
        )
        rows = r.fetchall()

    total = 0
    undone = 0
    overdue = 0
    for row in rows:
        journal_date = str(row[0])
        items = _parse_todo_items(row[1])
        for item in items:
            total += 1
            if not item.get('done', False):
                undone += 1
                if journal_date < today_str:
                    overdue += 1

    return jsonify(success=True, data={
        'total': total,
        'undone': undone,
        'overdue': overdue,
    })
