"""Add priority to journal page todos (view + edit)"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

changes = []

# ===== 1. showViewMode: add priority dot before todo text =====
old_view_todo = '''                const text = document.createElement('span');
                text.className = 'todo-text' + (item.done ? ' done-text' : '');
                text.textContent = item.text;'''

new_view_todo = '''                const priorityDot = document.createElement('span');
                priorityDot.className = 'todo-priority-dot todo-priority-' + (item.priority === 1 ? 'high' : item.priority === 3 ? 'low' : 'medium');
                priorityDot.style.cssText = 'margin-right:6px;';
                const text = document.createElement('span');
                text.className = 'todo-text' + (item.done ? ' done-text' : '');
                text.textContent = item.text;'''

if old_view_todo in c:
    c = c.replace(old_view_todo, new_view_todo, 1)
    changes.append('1. showViewMode: priority dot added')
else:
    print('WARN: showViewMode todo text not found')

# ===== 2. showViewMode: append priorityDot to li =====
old_append = '''                li.appendChild(num);
                li.appendChild(check);
                li.appendChild(text);
                todoList.appendChild(li);'''

new_append = '''                li.appendChild(num);
                li.appendChild(check);
                li.appendChild(priorityDot);
                li.appendChild(text);
                todoList.appendChild(li);'''

if old_append in c:
    c = c.replace(old_append, new_append, 1)
    changes.append('2. showViewMode: priorityDot appended')
else:
    print('WARN: showViewMode append not found')

# ===== 3. renderEditTodos: add priority select after input =====
old_edit_todo = '''            const del = document.createElement("button");
            del.className = "todo-del-btn";
            del.textContent = "×";
            del.addEventListener("click", () => { currentTodos.splice(idx, 1); renderEditTodos(); });
            li.appendChild(num);
            li.appendChild(check);
            li.appendChild(input);
            li.appendChild(del);'''

new_edit_todo = '''            const prioritySelect = document.createElement("select");
            prioritySelect.className = "todo-form-select";
            prioritySelect.style.cssText = "padding:4px 6px; font-size:12px; margin-left:4px;";
            prioritySelect.innerHTML = '<option value="1"' + (item.priority === 1 ? ' selected' : '') + '>高</option><option value="2"' + (item.priority === 2 ? ' selected' : '') + '>中</option><option value="3"' + (item.priority === 3 ? ' selected' : '') + '>低</option>';
            prioritySelect.addEventListener("change", (e) => { currentTodos[idx].priority = parseInt(e.target.value); });
            const del = document.createElement("button");
            del.className = "todo-del-btn";
            del.textContent = "×";
            del.addEventListener("click", () => { currentTodos.splice(idx, 1); renderEditTodos(); });
            li.appendChild(num);
            li.appendChild(check);
            li.appendChild(input);
            li.appendChild(prioritySelect);
            li.appendChild(del);'''

if old_edit_todo in c:
    c = c.replace(old_edit_todo, new_edit_todo, 1)
    changes.append('3. renderEditTodos: priority select added')
else:
    print('WARN: renderEditTodos del button not found')

# ===== 4. addTodoItem: add priority select in add row + read value =====
# First, add the select element in HTML
old_add_html = '''<div class="todo-add-row">
                            <input class="todo-add-input" id="todo-add-input" placeholder="添加新事项...">
                            <button class="todo-add-btn" id="todo-add-btn">添加</button>
                        </div>'''

new_add_html = '''<div class="todo-add-row">
                            <input class="todo-add-input" id="todo-add-input" placeholder="添加新事项...">
                            <select class="todo-form-select" id="todo-add-priority" style="padding:6px 10px; font-size:12px;">
                                <option value="1">高</option>
                                <option value="2" selected>中</option>
                                <option value="3">低</option>
                            </select>
                            <button class="todo-add-btn" id="todo-add-btn">添加</button>
                        </div>'''

if old_add_html in c:
    c = c.replace(old_add_html, new_add_html, 1)
    changes.append('4a. HTML: priority select in add row')
else:
    print('WARN: todo-add-row HTML not found')

# Now update addTodoItem function to read priority
old_add_fn = '''    function addTodoItem() {
        const input = document.getElementById("todo-add-input");
        const text = input.value.trim();
        if (!text) return;
        currentTodos.push({ text: text, done: false });
        input.value = "";
        renderEditTodos();
    }'''

new_add_fn = '''    function addTodoItem() {
        const input = document.getElementById("todo-add-input");
        const prioritySelect = document.getElementById("todo-add-priority");
        const text = input.value.trim();
        if (!text) return;
        const priority = prioritySelect ? parseInt(prioritySelect.value) : 2;
        currentTodos.push({ text: text, done: false, priority: priority });
        input.value = "";
        if (prioritySelect) prioritySelect.value = "2";
        renderEditTodos();
    }'''

if old_add_fn in c:
    c = c.replace(old_add_fn, new_add_fn, 1)
    changes.append('4b. addTodoItem: read priority value')
else:
    print('WARN: addTodoItem function not found')

path.write_text(c, encoding='utf-8')
for ch in changes:
    print('OK:', ch)
print(f'\nTotal: {len(changes)} changes')
