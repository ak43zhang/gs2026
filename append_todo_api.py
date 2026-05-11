"""Append TODO API routes to profile.py"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/routes/profile.py')
c = path.read_text(encoding='utf-8')

todo_routes = '''


# ============================================================
# 待办事项 API（聚合日志中的 todo_items）
# ============================================================

def _parse_todo_items(raw):
    """Parse todo_items JSON, return list of dicts."""
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
        return jsonify(success=False, message=\'\\u672a\\u767b\\u5f55\'), 401

    sort_by = request.args.get('sort', 'date')
    filter_done = request.args.get('done', '0')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT journal_date, todo_items FROM user_journals WHERE username = :u ORDER BY journal_date'),
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
            is_overdue = journal_date < today_str and not item_done
            todos.append({
                'date': journal_date,
                'index': idx,
                'text': item.get('text', ''),
                'done': item_done,
                'priority': item.get('priority', 2),
                'overdue': is_overdue,
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
        return jsonify(success=False, message=\'\\u672a\\u767b\\u5f55\'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')

    if not journal_date or index is None:
        return jsonify(success=False, message=\'\\u7f3a\\u5c11 date \\u6216 index\')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message=\'\\u65e5\\u5fd7\\u4e0d\\u5b58\\u5728\')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message=\'\\u7d22\\u5f15\\u65e0\\u6548\')

        items[index]['done'] = not items[index].get('done', False)

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message=\'\\u5207\\u6362\\u6210\\u529f\')


@profile_bp.route('/api/todo/update', methods=['POST'])
def todo_update():
    username = _current_user()
    if not username:
        return jsonify(success=False, message=\'\\u672a\\u767b\\u5f55\'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')

    if not journal_date or index is None:
        return jsonify(success=False, message=\'\\u7f3a\\u5c11 date \\u6216 index\')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message=\'\\u65e5\\u5fd7\\u4e0d\\u5b58\\u5728\')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message=\'\\u7d22\\u5f15\\u65e0\\u6548\')

        if 'text' in body:
            items[index]['text'] = body['text']
        if 'priority' in body:
            items[index]['priority'] = int(body['priority'])
        if 'done' in body:
            items[index]['done'] = bool(body['done'])

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message=\'\\u66f4\\u65b0\\u6210\\u529f\')


@profile_bp.route('/api/todo/delete', methods=['POST'])
def todo_delete_item():
    username = _current_user()
    if not username:
        return jsonify(success=False, message=\'\\u672a\\u767b\\u5f55\'), 401

    body = request.get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')

    if not journal_date or index is None:
        return jsonify(success=False, message=\'\\u7f3a\\u5c11 date \\u6216 index\')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message=\'\\u65e5\\u5fd7\\u4e0d\\u5b58\\u5728\')

        items = _parse_todo_items(row[0])
        if index < 0 or index >= len(items):
            return jsonify(success=False, message=\'\\u7d22\\u5f15\\u65e0\\u6548\')

        items.pop(index)

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items, ensure_ascii=False), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message=\'\\u5220\\u9664\\u6210\\u529f\')


@profile_bp.route('/api/todo/stats', methods=['GET'])
def todo_stats():
    username = _current_user()
    if not username:
        return jsonify(success=False, message=\'\\u672a\\u767b\\u5f55\'), 401

    today_str = str(date_type.today())
    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT journal_date, todo_items FROM user_journals WHERE username = :u'),
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
'''

c += todo_routes
path.write_text(c, encoding='utf-8')
print('OK: Appended 5 TODO API routes to profile.py')
