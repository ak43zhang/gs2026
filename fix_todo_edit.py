"""Fix profile.html: replace textarea with todo list + add missing JS functions"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

# 1. Replace the old textarea with edit-todo-list HTML
# HTML contains literal \n in placeholder attribute
search = '<textarea class="form-textarea" id="j-todo"'
idx = c.find(search)
if idx < 0:
    print("FAIL: Cannot find old textarea block start")
    exit(1)

# Find end of the textarea tag
end = c.find('</textarea>', idx)
end = c.find('\n', end) + 1  # include trailing newline

old_block = c[idx:end]
print(f"Found textarea block: {len(old_block)} chars")
print(f"  starts with: {old_block[:80]!r}")
print(f"  ends with: {old_block[-30:]!r}")

new_todo_block = '''<ul id="edit-todo-list" style="list-style:none; padding:0; margin:0 0 8px 0;"></ul>
                        <div class="todo-add-row">
                            <input class="todo-add-input" id="todo-add-input" placeholder="添加新事项...">
                            <button class="todo-add-btn" id="todo-add-btn">添加</button>
                        </div>\n'''

c = c[:idx] + new_todo_block + c[end:]
print("OK: Replaced textarea")

# 2. Check if renderEditTodos function body already exists
has_render_fn = 'function renderEditTodos()' in c
has_add_fn = 'function addTodoItem()' in c

if not has_render_fn:
    marker = '    // ===== 编辑模式 =====\n    function showEditMode'
    if marker not in c:
        print("FAIL: Could not find showEditMode marker!")
        exit(1)
    
    render_fn = (
        '    function renderEditTodos() {\n'
        '        const list = document.getElementById("edit-todo-list");\n'
        '        if (!list) { console.error("edit-todo-list not found!"); return; }\n'
        '        list.innerHTML = "";\n'
        '        currentTodos.forEach((item, idx) => {\n'
        '            const li = document.createElement("li");\n'
        '            li.className = "todo-item";\n'
        '            const num = document.createElement("span");\n'
        '            num.style.cssText = "color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;";\n'
        '            num.textContent = (idx + 1) + ".";\n'
        '            const check = document.createElement("div");\n'
        '            check.className = "todo-check" + (item.done ? " done" : "");\n'
        '            check.textContent = item.done ? " [OK]" : "";\n'
        '            check.addEventListener("click", () => { currentTodos[idx].done = !currentTodos[idx].done; renderEditTodos(); });\n'
        '            const input = document.createElement("input");\n'
        '            input.className = "todo-add-input";\n'
        '            input.style.flex = "1";\n'
        '            input.value = item.text;\n'
        '            input.addEventListener("input", () => { currentTodos[idx].text = input.value; });\n'
        '            const del = document.createElement("span");\n'
        '            del.className = "todo-del";\n'
        '            del.textContent = "x";\n'
        '            del.style.cssText = "cursor:pointer; color:#e74c3c; font-size:16px; padding:0 4px;";\n'
        '            del.addEventListener("click", () => { currentTodos.splice(idx, 1); renderEditTodos(); });\n'
        '            li.appendChild(num);\n'
        '            li.appendChild(check);\n'
        '            li.appendChild(input);\n'
        '            li.appendChild(del);\n'
        '            list.appendChild(li);\n'
        '        });\n'
        '    }\n'
        '\n'
    )
    c = c.replace(marker, render_fn + marker, 1)
    print("OK: Added renderEditTodos function")
else:
    print("SKIP: renderEditTodos already exists")

if not has_add_fn:
    add_fn = (
        '    function addTodoItem() {\n'
        '        const input = document.getElementById("todo-add-input");\n'
        '        const text = input.value.trim();\n'
        '        if (!text) return;\n'
        '        currentTodos.push({ text: text, done: false });\n'
        '        input.value = "";\n'
        '        renderEditTodos();\n'
        '    }\n'
        '\n'
    )
    c = c.replace(marker, add_fn + marker, 1)
    print("OK: Added addTodoItem function")
else:
    print("SKIP: addTodoItem already exists")

# 3. Add event listeners for add button + enter key
has_btn_listener = 'getElementById("todo-add-btn").addEventListener' in c

if not has_btn_listener:
    add_listeners = (
        '    // todo add button + enter key\n'
        '    document.getElementById("todo-add-btn").addEventListener("click", addTodoItem);\n'
        '    document.getElementById("todo-add-input").addEventListener("keydown", (e) => {\n'
        '        if (e.key === "Enter") { e.preventDefault(); addTodoItem(); }\n'
        '    });\n'
        '\n'
    )
    init_marker = '    // init\n    initCalendar();'
    if init_marker in c:
        c = c.replace(init_marker, add_listeners + init_marker, 1)
        print("OK: Added todo-add event listeners")
    else:
        print("FAIL: Could not find init marker!")
        exit(1)
else:
    print("SKIP: todo-add listeners already exist")

path.write_text(c, encoding='utf-8')
print("\nOK: All fixes applied!")
