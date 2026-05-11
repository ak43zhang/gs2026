"""Append 5 TODO API routes to profile.py"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/routes/profile.py')
c = path.read_text(encoding='utf-8')

# 1. /api/todo/list
todo_list_fn = '''

@profile_bp.route('/api/todo/list', methods=['GET'])
def todo_list():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    sort_by = request.args.get('sort', 'date')  # date | priority
    filter_done = request.args.get('done', '0')  # 0=未完成, 1=已完成, all=全部

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('''
                SELECT journal_date, todo_items
                FROM user_journals
                WHERE username = :u
                ORDER BY journal_date
            '''),
            {'u': username}
        )
        rows = r.fetchall()

    today = str(date_type.today())
    todos = []
    for row in rows:
        journal_date = str(row[0])
        items_raw = row[1] or '[]'
        items = json.loads(items_raw)
        if not isinstance(items, list):
            items = []
        for idx, item in enumerate(items):
            item_done = item.get('done', False) if isinstance(item, dict) else False
            if filter_done == '0' and item_done:
                continue
            if filter_done == '1' and not item_done:
                continue
            item_text = item.get('text', '') if isinstance(item, dict) else str(item)
            item_priority = item.get('priority', 2) if isinstance(item, dict) else 2
            todos.append({
                'date': journal_date,
                'index': idx,
                'text': item_text,
                'done': item_done,
                'priority': item_priority,
            })

    priority_map = {1: 0, 2: 1, 3: 2}
    if sort_by == 'priority':
        todos.sort(key=lambda x: (priority_map.get(x['priority'], 1), x['date']))
    else:
        todos.sort(key=lambda x: x['date'])

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
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = json.loads(row[0] or '[]')
        if not isinstance(items, list) or index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        items[index]['done'] = not items[index].get('done', False)
        if 'priority' not in items[index]:
            items[index]['priority'] = 2

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='切换成功')


@profile_bp.route('/api/todo/update', methods=['POST'])
def todo_update():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    body = request get_json(silent=True) or {}
    journal_date = body.get('date', '')
    index = body.get('index')

    if not journal_date or index is None:
        return jsonify(success=False, message='缺少 date 或 index')

    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = json.loads(row[0] or '[]')
        if not isinstance(items, list) or index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        if 'text' in body:
            items[index]['text'] = body['text']
        if 'priority' in body:
            items[index]['priority'] = int(body['priority'])
        if 'done' in body:
            items[index]['done'] = bool(body['done'])

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='更新成功')


@profile_bp.route('/api/todo/delete', methods=['POST'])
def todo_delete():
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
            text('SELECT todo_items FROM user_journals WHERE username = :u AND journal_date = :d'),
            {'u': username, 'd': journal_date}
        )
        row = r.fetchone()
        if not row:
            return jsonify(success=False, message='日志不存在')

        items = json.loads(row[0] or '[]')
        if not isinstance(items, list) or index < 0 or index >= len(items):
            return jsonify(success=False, message='索引无效')

        items.pop(index)

        conn.execute(
            text('UPDATE user_journals SET todo_items = :t WHERE username = :u AND journal_date = :d'),
            {'t': json.dumps(items), 'u': username, 'd': journal_date}
        )
        conn.commit()

    return jsonify(success=True, message='删除成功')


@profile_bp.route('/api/todo/stats', methods=['GET'])
def todo_stats():
    username = _current_user()
    if not username:
        return jsonify(success=False, message='未登录'), 401

    today = str(date_type.today())
    engine = _get_engine()
    with engine.connect() as conn:
        r = conn.execute(
            text('SELECT todo_items FROM user_journals WHERE username = :u'),
            {'u': username}
        )
        rows = r.fetchall()

    total = 0
    undone = 0
    today_undone = 0
    overdue = 0

    for row in rows:
        items = json.loads(row[0] or '[]')
        if not isinstance(items, list):
            continue
        for item in items:
            item_done = item.get('done', False) if isinstance(item, dict) else False
            total += 1
            if not item_done:
                undone += 1
                # date is from journal row, cannot directly get per item date
                # overdue dealt with in aggregator

    # Use todo_list endpoint to count overdue more accurately
    all_todos = []
    with engine.connect() as conn2:
        r2 = conn2.execute(
            text('SELECT journal_date, todo_items FROM user_journals WHERE username = :u ORDER BY journal_date'),
            {'u': username}
        )
        for row in r2:
            journal_date = str(row[0])
            items = json.loads(row[1] or '[]')
            if not isinstance(items, list):
                continue
            for item in items:
                item_done = item.get('done', False) if isinstance(item, dict) else False
                if item_done:
                    continue
                if journal_date <= today:
                    overdue += 1
                today_undone += 1

    return jsonify(success=True, data={
        'total': total,
        'undone': undone,
        'today_undone': today_undone if today_undone else undone,
        'overdue': overdue,
    })
'''

# Remove the trailing incomplete block and append
# Find the last valid block
lines = c.split('\n')
# The last line in file is "return jsonify(success=False, message='该日期无日志')"
# The file may be missing the closing of the else block

# Read the actual end of the file
print("Last 5 lines:")
for l in lines[-5:]:
    print(repr(l))
