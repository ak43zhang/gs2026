"""Fix: add todo form submit, _currentTodoList, filter/sort listeners, badge init"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

changes = []

# 1. Fix renderTodoGroups to save _currentTodoList
old_render = "    function renderTodoGroups(todos) {"
new_render = "    var _currentTodoList = [];\n    function renderTodoGroups(todos) {\n        _currentTodoList = todos;"
if old_render in c:
    # Need to also remove the duplicate opening brace
    c = c.replace(old_render, new_render, 1)
    # Remove the duplicate opening line that now has extra brace
    # Actually the replacement already includes the opening brace, so we need to remove the next line's brace
    # Let's check what comes after
    idx = c.find(new_render)
    # The original had "function renderTodoGroups(todos) {" followed by content
    # Now we have "var _currentTodoList = [];\n    function renderTodoGroups(todos) {\n        _currentTodoList = todos;"
    # followed by the original content starting with the next line
    changes.append('_currentTodoList declared + saved')

# 2. Add filter button listeners and sort listener
filter_js = '''
    // Todo filter buttons
    document.getElementById('filter-undone').addEventListener('click', function() {
        _todoFilterState = 'undone';
        document.querySelectorAll('.todo-filter-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        refreshTodoPage();
    });
    document.getElementById('filter-all').addEventListener('click', function() {
        _todoFilterState = 'all';
        document.querySelectorAll('.todo-filter-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        refreshTodoPage();
    });
    document.getElementById('filter-done').addEventListener('click', function() {
        _todoFilterState = 'done';
        document.querySelectorAll('.todo-filter-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        refreshTodoPage();
    });
    document.getElementById('todo-sort').addEventListener('change', function() {
        refreshTodoPage();
    });

    // Todo form submit
    document.getElementById('todo-form-submit').addEventListener('click', function() {
        var title = document.getElementById('todo-form-title').value.trim();
        var date = document.getElementById('todo-form-date').value;
        var priority = parseInt(document.getElementById('todo-form-priority').value) || 2;
        if (!title) { alert('请输入待办内容'); return; }
        if (!date) { alert('请选择日期'); return; }
        // Add to journal's todo_items for that date
        fetch('/api/journal/get?date=' + date).then(function(r) { return r.json(); }).then(function(res) {
            var existingTodos = [];
            var content = '';
            var remarks = '';
            var tags = '';
            var mood = '';
            if (res.success && res.data) {
                try { existingTodos = JSON.parse(res.data.todo_items || '[]'); } catch(e) { existingTodos = []; }
                content = res.data.content || '';
                remarks = res.data.remarks || '';
                tags = res.data.tags || '';
                mood = res.data.mood || '';
            }
            existingTodos.push({ text: title, done: false, priority: priority });
            return fetch('/api/journal/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: date,
                    content: content,
                    todo_items: JSON.stringify(existingTodos),
                    remarks: remarks,
                    tags: tags,
                    mood: mood
                })
            });
        }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.success) {
                document.getElementById('todo-form-title').value = '';
                refreshTodoPage();
            }
        });
    });
    document.getElementById('todo-form-title').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); document.getElementById('todo-form-submit').click(); }
    });

    // Init badge on page load
    _refreshTodoBadge();
    // Set default date for todo form
    document.getElementById('todo-form-date').value = new Date().toISOString().split('T')[0];
'''

# Insert after sidebar navigation block
sidebar_end_marker = "    // todo add button + enter key"
if sidebar_end_marker in c:
    c = c.replace(sidebar_end_marker, filter_js + '\n' + sidebar_end_marker, 1)
    changes.append('filter/sort/form listeners + badge init added')

path.write_text(c, encoding='utf-8')
for ch in changes:
    print('OK:', ch)
print(f'\nTotal: {len(changes)} changes')
