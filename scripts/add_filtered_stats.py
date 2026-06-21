"""Add filtered stats section to profile.html"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Add "总计统计" label to existing stats
old_stats_header = '''<p>来自日志中所有未完成事项</p>
                    </div>
                    <div class="todo-stats">'''

new_stats_header = '''<p>来自日志中所有未完成事项</p>
                    </div>
                    <div style="font-size:11px;color:#8a8fa3;margin-bottom:4px;font-weight:600;">📊 总计统计（全部时间）</div>
                    <div class="todo-stats">'''

if old_stats_header in content:
    content = content.replace(old_stats_header, new_stats_header)
    changes += 1
    print('[1] Added total stats label')
else:
    print('[1] Stats header not found')

# 2. Add filtered stats section after the existing stats block
old_filters = '''<div class="todo-filters">'''

new_filtered_stats = '''<div id="todo-filtered-stats" style="display:none;margin-top:8px;">
                        <div style="font-size:11px;color:#8a8fa3;margin-bottom:4px;font-weight:600;">📋 <span id="filtered-stats-label">当前筛选</span></div>
                        <div class="todo-stats">
                            <div class="todo-stat-card">
                                <div class="todo-stat-num" id="fstat-undone">0</div>
                                <div class="todo-stat-label">未完成</div>
                            </div>
                            <div class="todo-stat-card">
                                <div class="todo-stat-num" id="fstat-total">0</div>
                                <div class="todo-stat-label">总计</div>
                            </div>
                            <div class="todo-stat-card deferred">
                                <div class="todo-stat-num" id="fstat-deferred">0</div>
                                <div class="todo-stat-label">暂缓</div>
                            </div>
                            <div class="todo-stat-card overdue">
                                <div class="todo-stat-num" id="fstat-overdue">0</div>
                                <div class="todo-stat-label">逾期</div>
                            </div>
                        </div>
                    </div>
                    <div class="todo-filters">'''

if old_filters in content:
    content = content.replace(old_filters, new_filtered_stats, 1)
    changes += 1
    print('[2] Added filtered stats section')
else:
    print('[2] Filters marker not found')

# 3. Update JS: split stats loading into total + filtered
old_stats_js = """fetch('/api/todo/stats').then(function(r2) { return r2.json(); }).then(function(res2) {
                if (res2.success) {
                    document.getElementById('stat-undone').textContent = res2.data.undone || 0;
                    document.getElementById('stat-total').textContent = res2.data.total || 0;
                    document.getElementById('stat-deferred').textContent = res2.data.deferred || 0;
                    document.getElementById('stat-overdue').textContent = res2.data.overdue || 0;
                }
                _refreshTodoBadge();
            });"""

new_stats_js = """// 总计统计（全部时间）
            fetch('/api/todo/stats').then(function(r2) { return r2.json(); }).then(function(res2) {
                if (res2.success) {
                    document.getElementById('stat-undone').textContent = res2.data.undone || 0;
                    document.getElementById('stat-total').textContent = res2.data.total || 0;
                    document.getElementById('stat-deferred').textContent = res2.data.deferred || 0;
                    document.getElementById('stat-overdue').textContent = res2.data.overdue || 0;
                }
                _refreshTodoBadge();
            });
            // 筛选统计（按月份）
            var _fsMonth = document.getElementById('todo-month-filter').value;
            var _fsPanel = document.getElementById('todo-filtered-stats');
            if (_fsMonth) {
                fetch('/api/todo/stats?month=' + _fsMonth).then(function(r3) { return r3.json(); }).then(function(res3) {
                    if (res3.success) {
                        document.getElementById('fstat-undone').textContent = res3.data.undone || 0;
                        document.getElementById('fstat-total').textContent = res3.data.total || 0;
                        document.getElementById('fstat-deferred').textContent = res3.data.deferred || 0;
                        document.getElementById('fstat-overdue').textContent = res3.data.overdue || 0;
                        document.getElementById('filtered-stats-label').textContent = _fsMonth + ' 统计';
                    }
                });
                _fsPanel.style.display = '';
            } else {
                _fsPanel.style.display = 'none';
            }"""

if old_stats_js in content:
    content = content.replace(old_stats_js, new_stats_js)
    changes += 1
    print('[3] Updated stats JS')
else:
    print('[3] Stats JS not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nDone: {changes} changes')
