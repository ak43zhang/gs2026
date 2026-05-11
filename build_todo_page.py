"""Add sidebar todo item + todo page HTML + CSS + JS to profile.html"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

changes = []

# ===== A. Sidebar: add todo item after journal =====
old_sidebar_journal_end = '''                <span>日志</span>
                </div>'''
new_sidebar_journal_end = '''                <span>日志</span>
                </div>
                <div class="sidebar-item" data-page="todo">
                    <span class="sidebar-icon">*</span>
                    <span>待办</span>
                    <span class="sidebar-badge" id="todo-badge">0</span>
                </div>'''
if old_sidebar_journal_end in c:
    c = c.replace(old_sidebar_journal_end, new_sidebar_journal_end)
    changes.append('sidebar todo item added')
else:
    print('FAIL: sidebar journal end not found')
    exit(1)

# ===== C. CSS styles =====
badge_css = '''
        .sidebar-badge { margin-left: auto; background: #e74c3c; color: #fff; font-size: 11px; min-width: 20px; height: 20px; border-radius: 10px; display: flex; align-items: center; justify-content: center; padding: 0 5px; font-weight: 600; }
        .warm-page .sidebar-badge { background: #e74c3c; color: #fff; }

        /* ===== 待办页面 ===== */
        .todo-page-content { padding: 0; }
        .todo-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
        .todo-header h2 { margin: 0; font-size: 18px; color: #2d3748; }
        .warm-page .todo-header h2 { color: #3d3d3d; }
        .todo-stats { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
        .todo-stat-card { flex: 1; min-width: 100px; padding: 12px 16px; background: rgba(255,255,255,0.85); border-radius: 10px; text-align: center; }
        .todo-stat-num { font-size: 24px; font-weight: 700; color: #667eea; }
        .todo-stat-label { font-size: 12px; color: #8a8fa3; margin-top: 2px; }
        .todo-stat-card.overdue .todo-stat-num { color: #e74c3c; }
        .todo-filters { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
        .todo-filter-btn { padding: 5px 14px; border-radius: 16px; border: 1px solid #dde1ea; background: #fff; cursor: pointer; font-size: 12px; color: #5a5e72; transition: all 0.2s; }
        .todo-filter-btn.active { background: #667eea; color: #fff; border-color: #667eea; }
        .warm-page .todo-filter-btn { background: rgba(255,255,255,0.7); }

        .todo-group { margin-bottom: 16px; }
        .todo-group-header { font-size: 14px; font-weight: 600; padding: 8px 0 6px; color: #2d3748; border-bottom: 1px solid rgba(0,0,0,0.06); margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
        .warm-page .todo-group-header { color: #3d3d3d; border-bottom-color: rgba(0,0,0,0.04); }
        .todo-group-overdue { color: #e74c3c; }
        .todo-item-row { display: flex; align-items: center; gap: 8px; padding: 7px 10px; background: rgba(255,255,255,0.88); border-radius: 8px; margin-bottom: 5px; transition: background 0.15s; cursor: default; }
        .todo-item-row:hover { background: rgba(255,255,255,1); }
        .todo-item-row.overdue-row { border-left: 3px solid #e74c3c; }
        .todo-item-row.done-row { opacity: 0.55; }
        .todo-check-circle { width: 22px; height: 22px; border-radius: 50%; border: 2px solid #ccc; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 13px; flex-shrink: 0; transition: all 0.2s; }
        .todo-check-circle.checked { background: #667eea; border-color: #667eea; color: #fff; }
        .todo-priority-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .todo-priority-high { background: #e74c3c; }
        .todo-priority-medium { background: #f39c12; }
        .todo-priority-low { background: #27ae60; }
        .todo-item-text { flex: 1; font-size: 14px; color: #2d3748; word-break: break-word; }
        .todo-item-text.done-text { text-decoration: line-through; color: #aaa; }
        .warm-page .todo-item-text { color: #3d3d3d; }
        .todo-item-actions { display: flex; gap: 4px; flex-shrink: 0; }
        .todo-action-btn { padding: 2px 6px; border: none; background: transparent; cursor: pointer; font-size: 12px; color: #999; border-radius: 4px; }
        .todo-action-btn:hover { background: rgba(0,0,0,0.06); color: #333; }
        .todo-action-btn.del-btn:hover { background: #fee; color: #e74c3c; }

        .todo-add-form { display: flex; gap: 8px; padding: 12px; background: rgba(255,255,255,0.88); border-radius: 10px; margin-top: 8px; flex-wrap: wrap; align-items: center; }
        .todo-form-input { flex: 1; min-width: 150px; padding: 8px 12px; border: 1px solid #dde1ea; border-radius: 6px; font-size: 13px; background: #fff; color: #3d3d3d; }
        .todo-form-input:focus { outline: none; border-color: #667eea; }
        .todo-form-select { padding: 8px 10px; border: 1px solid #dde1ea; border-radius: 6px; font-size: 13px; background: #fff; color: #3d3d3d; }
        .todo-form-date { padding: 8px 10px; border: 1px solid #dde1ea; border-radius: 6px; font-size: 13px; background: #fff; color: #3d3d3d; }
        .todo-submit-btn { padding: 8px 18px; background: #667eea; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
        .todo-submit-btn:hover { background: #5568d3; }
        .warm-page .todo-form-input, .warm-page .todo-form-select, .warm-page .todo-form-date { background: rgba(255,255,255,0.6); }
        .todo-edit-inline { display: none; gap: 4px; align-items: center; }
        .todo-edit-inline input { flex: 1; padding: 4px 8px; border: 1px solid #667eea; border-radius: 4px; font-size: 13px; }
        .todo-edit-priority-select { padding: 4px 6px; border: 1px solid #dde1ea; border-radius: 4px; font-size: 12px; }
        .todo-edit-inline.show { display: flex; }
        .todo-text-display { display: flex; align-items: center; gap: 6px; flex: 1; }

        @media(max-width: 640px) {
            .todo-filters { flex-wrap: wrap; }
            .todo-add-form { flex-direction: column; }
            .todo-form-input { min-width: 100%; }
        }
'''

# Insert before </style>
style_end = '</style>'
if style_end in c:
    c = c.replace(style_end, badge_css + '\n</style>', 1)
    changes.append('added todo CSS')
else:
    print('FAIL: </style> not found')
    exit(1)

# ===== D. Add page-todo section in HTML =====
# Find the page-journal closing div and the page-placeholders opening
lines = c.split('\n')
page_journal_close = None
page_placeholders_open = None
for i, line in enumerate(lines):
    # Find the end of page-journal (the closing </div> of the main journal section)
    # Find start of page-placeholders
    if 'id="page-placeholders"' in line and page_placeholders_open is None:
        page_placeholders_open = i
    if page_placeholders_open and page_journal_close is None:
        # Look for the </div> that closes page-journal — it should be just before page-placeholders
        pass

# Simpler approach: search for the HTML pattern
journal_section_end_fwd = c.find('<!-- >')
page_todo_html = '''

                <!-- ===== 待办页面 ===== -->
                <main class="profile-content todo-page-content" id="page-todo" style="display:none;">
                    <div class="content-header">
                        <h2>待办事项汇总</h2>
                        <p>来自日志中所有未完成事项</p>
                    </div>
                    <div class="todo-stats">
                        <div class="todo-stat-card">
                            <div class="todo-stat-num" id="stat-undone">0</div>
                            <div class="todo-stat-label">未完成</div>
                        </div>
                        <div class="todo-stat-card">
                            <div class="todo-stat-num" id="stat-total">0</div>
                            <div class="todo-stat-label">总计</div>
                        </div>
                        <div class="todo-stat-card overdue">
                            <div class="todo-stat-num" id="stat-overdue">0</div>
                            <div class="todo-stat-label">逾期</div>
                        </div>
                    </div>
                    <div class="todo-filters">
                        <button class="todo-filter-btn active" id="filter-undone">未完成</button>
                        <button class="todo-filter-btn" id="filter-all">全部</button>
                        <button class="todo-filter-btn" id="filter-done">已完成</button>
                        <span style="margin-left:auto; display:flex; gap:4px; align-items:center;">
                            <label style="font-size:12px; color:#8a8fa3;">排序:</label>
                            <select id="todo-sort" style="padding:4px 8px; border:1px solid #dde1ea; border-radius:4px; font-size:12px; background:#fff; color:#3d3d3d;">
                                <option value="date">日期</option>
                                <option value="priority">优先级</option>
                            </select>
                        </span>
                    </div>
                    <div id="todo-list-container">
                        <div id="todo-loading" style="text-align:center; padding:40px; color:#8a8fa3; font-size:14px;">加载中...</div>
                        <div id="todo-groups"></div>
                    </div>
                    <div class="todo-add-form">
                        <input class="todo-form-input" id="todo-form-title" placeholder="待办内容..." style="flex:2;">
                        <input class="todo-form-date" id="todo-form-date" type="date">
                        <select class="todo-form-select" id="todo-form-priority">
                            <option value="1">高</option>
                            <option value="2" selected>中</option>
                            <option value="3">低</option>
                        </select>
                        <button class="todo-submit-btn" id="todo-form-submit">+ 添加</button>
                    </div>
                </main>

'''

# Find the page-placeholders main opening tag
placeholders_tag = 'id="page-placeholders"'
idx = c.find(placeholders_tag)
if idx < 0:
    print('FAIL: page-placeholders not found')
    exit(1)
# Insert before it
c = c[:idx] + page_todo_html + c[idx:]
changes.append('todo page HTML inserted')

# ===== E. JS: sidebar navigation for todo =====
old_sidebar_nav = '''            } else if (sidebarItem.dataset.page === 'journal') {'''
new_sidebar_nav = '''            } else if (sidebarItem.dataset.page === 'todo') {
                showTodoPage();
                return;
            } else if (sidebarItem.dataset.page === 'journal') {'''
if old_sidebar_nav in c:
    c = c.replace(old_sidebar_nav, new_sidebar_nav)
    changes.append('sidebar nav -> journal')

# Fix the journal nav to be specific
old_journal_nav = "            } else if (sidebarItem.dataset.page === 'journal') {"
old_journal_body = "                showPage('journal');"
# These should already work, but let's verify

# ===== F. Add showTodoPage + todo JS functions =====
todo_js = '''
    // ===== 待办页面 =====
    let _todoEditingDate = null;
    let _todoEditingIndex = null;

    function showTodoPage() {
        document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
        document.querySelector('[data-page="todo"]').classList.add('active');
        document.getElementById('page-journal').style.display = 'none';
        document.getElementById('page-placeholders').style.display = 'none';
        document.getElementById('page-todo').style.display = '';
        _todoEditingDate = null;
        _todoEditingIndex = null;
        refreshTodoPage();

        // default today
        document.getElementById('todo-form-date').value = new Date().toISOString().split('T')[0];
    }

    var _todoFilterState = 'undone';

    function refreshTodoPage() {
        var sortBy = document.getElementById('todo-sort').value;
        var filterDone = _todoFilterState === 'done' ? '1' : _todoFilterState === 'all' ? 'all' : '0';
        var url = '/api/todo/list?sort=' + sortBy + '&done=' + filterDone;
        fetch(url).then(function(r) { return r.json(); }).then(function(res) {
            if (!res.success) { document.getElementById('todo-groups').innerHTML = '<p style="color:#e74c3c;">' + res.message + '</p>'; return; }
            renderTodoGroups(res.data);
            // Update stats
            fetch('/api/todo/stats').then(function(r2) { return r2.json(); }).then(function(res2) {
                if (res2.success) {
                    document.getElementById('stat-undone').textContent = res2.data.undone || 0;
                    document.getElementById('stat-total').textContent = res2.data.total || 0;
                    document.getElementById('stat-overdue').textContent = res2.data.overdue || 0;
                }
                _refreshTodoBadge();
            });
        });
    }

    function renderTodoGroups(todos) {
        var groupsEl = document.getElementById('todo-groups');
        if (todos.length === 0) { groupsEl.innerHTML = '<p style="color:#8a8fa3; text-align:center; padding:40px; font-size:14px;">没有待办事项</p>'; return; }

        var today = new Date().toISOString().split('T')[0];
        var groups = {};
        todos.forEach(function(t) {
            if (!groups[t.date]) groups[t.date] = [];
            groups[t.date].push(t);
        });

        var html = '';
        Object.keys(groups).sort().forEach(function(gdate) {
            var items = groups[gdate];
            var isToday = gdate === today;
            var isPast = gdate < today;
            var label = gdate;
            var overCount = 0;
            items.forEach(function(it) { if (it.overdue) overCount++; });
            if (isPast && overCount > 0) label += ' (' + overCount + ' 逾期)';
            else if (isToday && !_todoEditingDate) label += ' (今天)';
            else if (isPast) label += ' (已过)';

            var indent = '';
            if (isPast || isToday);

            html += '<div class="todo-group"><div class="todo-group-header" style="' + (overCount > 0 ? 'color:#e74c3c;' : '') + '">' + label + '</div>';
            items.forEach(function(item, idx) {
                var priorityMap = {1: 'high', 2: 'medium', 3: 'low'};
                var priorityLabel = {1: ' ', 2: ' ', 3: ' '};
                var pClass = 'todo-priority-' + (priorityMap[item.priority] || 'medium');
                var stateClass = item.done ? 'checked' : '';
                var rowClass = item.done ? 'done-row' : '';
                if (item.overdue) rowClass += ' overflow-row';

                // Build text with optional inline edit
                if (_todoEditingDate === item.date && _todoEditingIndex === item.index) {
                    html += '<div class="todo-item-row">';
                    html += '<div class="todo-check-circle"></div>';
                    html += '<span class="todo-priority-dot ' + pClass + '"></span>';
                    html += '<input class="todo-form-input" id="todo-inline-edit-input" value="' + escapeHtml(item.text) + '" style="flex:1;">';
                    html += '<select class="todo-form-select todo-edit-priority-select" id="todo-inline-priority">';
                    html += '<option value="1" ' + (item.priority === 1 ? 'selected' : '') + '>高</option>';
                    html += '<option value="2" ' + (item.priority === 2 ? 'selected' : '') + '>中</option>';
                    html += '<option value="3" ' + (item.priority === 3 ? 'selected' : '') + '>低</option>';
                    html += '</select>';
                    html += '<button class="todo-action-btn" onclick="saveTodoEdit(\'' + item.date + '\', ' + item.index + ')" title="保存">*</button>';
                    html += '<button class="todo-action-btn" onclick="cancelTodoEdit()" title="取消">x</button>';
                    html += '</div>';
                    // Focus inline edit
                    setTimeout(function() { var el = document.getElementById('todo-inline-edit-input'); if (el) { el.focus(); el.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); saveTodoEdit(item.date, item.index); } }); } }, 50);
                } else {
                    html += '<div class="todo-item-row ' + rowClass + '">';
                    html += '<div class="todo-check-circle ' + stateClass + '" onclick="toggleTodoInList(\'' + item.date + '\', ' + item.index + ')">' + (item.done ? '*' : '') + '</div>';
                    html += '<span class="todo-priority-dot ' + pClass + '" title="' + priorityLabel[item.priority] + '"></span>';
                    html += '<span class="todo-item-text' + (item.done ? ' done-text' : '') + '" onclick="toggleTodoInList(\'' + item.date + '\', ' + item.index + ')">' + escapeHtml(item.text) + '</span>';
                    html += '<div class="todo-item-actions">';
                    html += '<button class="todo-action-btn" onclick="editTodoInline(\'' + item.date + '\', ' + item.index + ')" title="*">*</button>';
                    html += '<button class="todo-del-btn todo-action-btn" onclick="deleteTodoItem(\'' + item.date + '\', ' + item.index + ')" title="*">x</button>';
                    html += '</div>';
                    html += '</div>';
                }
            });
            html += '</div>';
        });
        groupsEl.innerHTML = html;
    }

    function toggleTodoInList(date, index) {
        fetch('/api/todo/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: date, index: index })
        }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) refreshTodoPage();
        });
    }

    function saveTodoEdit(date, index) {
        var input = document.getElementById('todo-inline-edit-input');
        var priorityEl = document.getElementById('todo-inline-priority');
        var text = input ? input.value.trim() : '';
        if (!text) return;
        fetch('/api/todo/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: date, index: index, text: text, priority: priorityEl ? parseInt(priorityEl.value) : 2 })
        }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) { _todoEditingDate = null; refreshTodoPage(); }
        });
    }

    function cancelTodoEdit() {
        _todoEditingDate = null; _todoEditingIndex = null; renderTodoGroups(_currentTodoList || []);
    }

    function editTodoInline(date, index) {
        _todoEditingDate = date; _todoEditingIndex = index;
        renderTodoGroups(_currentTodoList || []);
    }

    function deleteTodoItem(date, index) {
        if (!confirm('确定删除?')) return;
        fetch('/api/todo/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: date, index: index })
        }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) refreshTodoPage();
        });
    }

    function _refreshTodoBadge() {
        fetch('/api/todo/stats').then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) {
                var badge = document.getElementById('todo-badge');
                if (badge) badge.textContent = res.data.undone || 0;
            }
        });
    }

    function escapeHtml(str) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(str || ''));
        return d.innerHTML;
    }

'''

# Find init and insert before it
init_marker = '    // init\n    initCalendar();'
if init_marker in c:
    c = c.replace(init_marker, todo_js + init_marker, 1)
    changes.append('todo JS added')

path.write_text(c, encoding='utf-8')
for ch in changes:
    print('OK:', ch)
print('\nTotal:', len(changes), 'changes')
