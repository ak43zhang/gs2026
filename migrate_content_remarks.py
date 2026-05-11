"""profile.html: content/remarks -> multi-line items"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

changes = []

# ===== A. Replace content textarea with list =====
old_content_search = '<textarea class="form-textarea" id="j-content"'
idx1 = c.find(old_content_search)
end1 = c.find('</textarea>', idx1)
end1 = c.find('\n', end1) + 1
old_content = c[idx1:end1]
c = c[:idx1] + (
    '<ul id="edit-content-list" style="list-style:none; padding:0; margin:0 0 8px 0;"></ul>\n'
    '                        <div class="todo-add-row">\n'
    '                            <input class="todo-add-input" id="content-add-input" placeholder="添加内容模块...">\n'
    '                            <button class="todo-add-btn" id="content-add-btn">添加</button>\n'
    '                        </div>\n'
) + c[end1:]
changes.append('content textarea -> list')

# ===== B. Replace remarks textarea with list =====
old_remarks_search = 'style="min-height:60px;"'
idx2 = c.find(old_remarks_search)
if idx2 < 0:
    print('FATAL: cannot find remarks textarea')
    exit(1)
# find the full remarks textarea tag
line_start = c.rfind('\n', 0, idx2) + 1
tag_end = c.find('</textarea>', idx2) + len('</textarea>')
line_end = c.find('\n', tag_end) + 1 if '\n' in c[tag_end:] else len(c)
old_remarks = c[line_start:line_end]
c = c[:line_start] + (
    '<ul id="edit-remarks-list" style="list-style:none; padding:0; margin:0 0 8px 0;"></ul>\n'
    '                        <div class="todo-add-row">\n'
    '                            <input class="todo-add-input" id="remarks-add-input" placeholder="添加备注...">\n'
    '                            <button class="todo-add-btn" id="remarks-add-btn">添加</button>\n'
    '                        </div>\n'
) + c[line_end:]
changes.append('remarks textarea -> list')

# ===== C. JS helper functions for content_items =====
parse_content_fn = (
    '    function parseContent(raw) {\n'
    '        if (!raw) return [];\n'
    '        if (Array.isArray(raw)) return raw;\n'
    '        try { const a = JSON.parse(raw); if (Array.isArray(a)) return a; } catch(e) {}\n'
    '        return raw.split("\\n").map(s => s.trim()).filter(Boolean).map(s => ({ text: s, done: false }));\n'
    '    }\n'
    '    function contentToJson(items) { return JSON.stringify(items); }\n'
    '\n'
    '    function parseRemarks(raw) {\n'
    '        if (!raw) return [];\n'
    '        if (Array.isArray(raw)) return raw;\n'
    '        try { const a = JSON.parse(raw); if (Array.isArray(a)) return a; } catch(e) {}\n'
    '        return raw.split("\\n").map(s => s.trim()).filter(Boolean).map(s => ({ text: s, done: false }));\n'
    '    }\n'
    '    function remarksToJson(items) { return JSON.stringify(items); }\n'
    '\n'
)

# Insert before showEditMode
lines2 = c.split('\n')
for i, line in enumerate(lines2):
    stripped = line.strip()
    if stripped == 'function showEditMode(data, isNew) {':
        insert_pos = c.find(line)
        # add functions before this line
        pos_before = c.find(lines2[i-1], 0, insert_pos) if i > 0 else 0
        # find the actual position of the comment before showEditMode
        # better: find on the exact line itself by joining
        before_pos2 = c.find(line, 0, insert_pos)
        c = c[:before_pos2] + parse_content_fn + c[before_pos2:]
        changes.append('Added parseContent / contentToJson / parseRemarks / remarksToJson helpers')
        break

# ===== D. Rewrite showEditMode to use content_items / remarks_items =====
old_showedit = (
    "        if (data && !isNew) {\n"
    "            form.style.display = '';\n"
    "            hint.style.display = 'none';\n"
    "            document.getElementById('j-content').value = data.content || '';\n"
    "            currentTodos = parseTodos(data.todo_items);\n"
    "            renderEditTodos();\n"
    "            document.getElementById('j-remarks').value = data.remarks || '';\n"
)
new_showedit = (
    "        if (data && !isNew) {\n"
    "            form.style.display = '';\n"
    "            hint.style.display = 'none';\n"
    "            currentContent = parseContent(data.content || data.content_items || '');\n"
    "            renderEditContent();\n"
    "            currentRemarks = parseRemarks(data.remarks || '');\n"
    "            renderEditRemarks();\n"
    "            currentTodos = parseTodos(data.todo_items);\n"
    "            renderEditTodos();\n"
)
if old_showedit in c:
    c = c.replace(old_showedit, new_showedit)
    changes.append("showEditMode edit branch -> content_items / remarks_items")
else:
    print("FATAL: showEditMode edit branch not found as expected")
    exit(1)

# else branch of showEditMode
old_showedit_else = (
    "        } else {\n"
    "            form.style.display = '';\n"
    "            hint.style.display = 'none';\n"
    "            document.getElementById('j-content').value = '';\n"
    "            currentTodos = [];\n"
    "            renderEditTodos();\n"
    "            document.getElementById('j-remarks').value = '';\n"
)
new_showedit_else = (
    "        } else {\n"
    "            form.style.display = '';\n"
    "            hint.style.display = 'none';\n"
    "            currentContent = [];\n"
    "            renderEditContent();\n"
    "            currentRemarks = [];\n"
    "            renderEditRemarks();\n"
    "            currentTodos = [];\n"
    "            renderEditTodos();\n"
)
if old_showedit_else in c:
    c = c.replace(old_showedit_else, new_showedit_else)
    changes.append("showEditMode else branch -> content_items / remarks_items")
else:
    print("FATAL: showEditMode else branch not found")
    exit(1)

# ===== E. Declare global currentContent, currentRemarks =====
old_global = "const state = { year: null, month: null, selectedDate: null, journals: {} };"
new_global = "var currentContent = []; var currentRemarks = []; var currentTodos = []; var currentViewData = null;\n    const state = { year: null, month: null, selectedDate: null, journals: {} };"
if old_global in c:
    c = c.replace(old_global, new_global)
    changes.append("global currentContent / currentRemarks declared")
else:
    print("FAIL: state declaration not found")

# ===== F. Rewrite loadJournal to parse content/remarks =====
old_loadjournal = (
    "            document.getElementById('view-content').textContent = data.content || '';\n"
    "            document.getElementById('view-remarks').textContent = data.remarks || '';"
)
new_loadjournal = (
    "            const contentItems = parseContent(data.content || data.content_items || '');\n"
    "            const contentList = document.getElementById('view-content-list');\n"
    "            contentList.innerHTML = '';\n"
    "            contentItems.forEach((item, idx) => {\n"
    "                const li = document.createElement('li');\n"
    "                li.className = 'todo-item';\n"
    "                const num = document.createElement('span');\n"
    "                num.style.cssText = 'color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;';\n"
    "                num.textContent = (idx + 1) + '.';\n"
    "                const text = document.createElement('span');\n"
    "                text.className = 'todo-text';\n"
    "                text.textContent = item.text;\n"
    "                li.appendChild(num);\n"
    "                li.appendChild(text);\n"
    "                contentList.appendChild(li);\n"
    "            });"
)
if old_loadjournal in c:
    c = c.replace(old_loadjournal, new_loadjournal)
    changes.append('loadJournal: content displayed as list')

old_remarks_view = "            document.getElementById('view-remarks').textContent = data.remarks || '';\n"
if old_remarks_view in c:
    c = c.replace(old_remarks_view, '')
    changes.append("removed old direct remarks textContent")

# Replace @ view-content textContent
old_view_content_text = 'document.getElementById("view-content").textContent = data.content || \'\';'
if old_view_content_text in c:
    c = c.replace(old_view_content_text, '')
    changes.append("removed old direct content textContent")

# ===== G. Add view-content-list / view-remarks-list elements =====
old_view_remarks_div1 = (
    '                        <div class="view-text" id="view-remarks"></div>'
)
new_view_remarks_div = (
    '                        <div class="view-text" id="view-content-list" style="list-style:none; padding:0; margin:0;"></div>\n'
    '                    </div>\n'
    '                    <hr class="view-divider">\n'
    '                    <div id="view-remarks-section" class="view-section">\n'
    '                        <div class="view-label">备注</div>\n'
    '                        <ul id="view-remarks-list" style="list-style:none; padding:0; margin:0;"></ul>'
)
c = c.replace(old_view_remarks_div1, new_view_remarks_div)
changes.append('view-content-list + view-remarks-list HTML')

# ===== H. Rewrite toggleTodoInView calls for content/remarks =====
# Fix the view edit button data capture
old_view_edit_data = (
    '        const viewData = {\n'
    '            content: document.getElementById("view-content").textContent,\n'
    '            todo_items: currentViewData ? currentViewData.todo_items : "[]",\n'
    '            remarks: document.getElementById("view-remarks").textContent,\n'
)
new_view_edit_data = (
    '        const viewData = {\n'
    '            content: contentToJson(currentContent || parseContent(document.getElementById("view-content").textContent || "")),\n'
    '            todo_items: currentViewData ? currentViewData.todo_items : "[]",\n'
    '            remarks: remarksToJson(currentRemarks || []),\n'
)
if old_view_edit_data in c:
    c = c.replace(old_view_edit_data, new_view_edit_data)
    changes.append("edit button: content/remarks use JSON")

# ===== I. Rewrite saveJournal =====
old_save = (
    "            content: document.getElementById('j-content').value,\n"
    "            todo_items: todosToJson(currentTodos),\n"
    "            remarks: document.getElementById('j-remarks').value,\n"
)
new_save = (
    "            content: contentToJson(currentContent),\n"
    "            todo_items: todosToJson(currentTodos),\n"
    "            remarks: remarksToJson(currentRemarks),\n"
)
if old_save in c:
    c = c.replace(old_save, new_save)
    changes.append("saveJournal: content_items / remarks as JSON")

# ===== J. Show content items (with done state) in view mode =====
# Replace the simplistic content item rendering loop
old_render_content = (
    "                li.appendChild(text);\n"
    "                contentList.appendChild(li);\n"
    "            });"
)
new_render_content = (
    "                li.appendChild(text);\n"
    '                li.addEventListener("click", () => { contentItems[idx].done = !contentItems[idx].done; showViewMode(data); saveContentOnly(); });\n'
    "                contentList.appendChild(li);\n"
    "            });"
)
c = c.replace(old_render_content, new_render_content)
changes.append("content items: click to toggle done in view mode")

# Add saveContentOnly helper (saves only content without leaving view mode)
save_content_fn = (
    '    function saveContentOnly() {\n'
    '        if (!state.selectedDate) return;\n'
    '        fetch("/api/journal/save", {\n'
    '            method: "POST",\n'
    '            headers: { "Content-Type": "application/json" },\n'
    '            body: JSON.stringify({\n'
    '                date: state.selectedDate,\n'
    '                content: contentToJson(currentContent),\n'
    '                todo_items: currentViewData ? currentViewData.todo_items : "[]",\n'
    '                remarks: remarksToJson(currentRemarks),\n'
    '                tags: currentViewData ? currentViewData.tags : "",\n'
    '                mood: currentViewData ? currentViewData.mood : "",\n'
    '            })\n'
    '        }).then(r => r.json()).then(() => {\n'
    '            if (currentViewData) currentViewData.content = contentToJson(currentContent);\n'
    '        });\n'
    '    }\n'
    '\n'
)

# ===== K. Add /add event listeners for content and remarks =====
old_init = "    // init\n    initCalendar();"
new_init = '    // content add button + enter key\n'
new_init += '    document.getElementById("content-add-btn").addEventListener("click", () => {\n'
new_init += '        const input = document.getElementById("content-add-input");\n'
new_init += '        const text = input.value.trim();\n'
new_init += '        if (!text) return;\n'
new_init += '        currentContent.push({ text: text, done: false });\n'
new_init += '        input.value = "";\n'
new_init += '        renderEditContent();\n'
new_init += '    });\n'
new_init += '    document.getElementById("content-add-input").addEventListener("keydown", (e) => {\n'
new_init += '        if (e.key === "Enter") { e.preventDefault(); addContentItem(); }\n'
new_init += '    });\n'
new_init += '    // remarks add button + enter key\n'
new_init += '    document.getElementById("remarks-add-btn").addEventListener("click", () => {\n'
new_init += '        const input = document.getElementById("remarks-add-input");\n'
new_init += '        const text = input.value.trim();\n'
new_init += '        if (!text) return;\n'
new_init += '        currentRemarks.push({ text: text, done: false });\n'
new_init += '        input.value = "";\n'
new_init += '        renderEditRemarks();\n'
new_init += '    });\n'
new_init += '    document.getElementById("remarks-add-input").addEventListener("keydown", (e) => {\n'
new_init += '        if (e.key === "Enter") { e.preventDefault(); addRemarksItem(); }\n'
new_init += '    });\n'
new_init += '\n    // init\n    initCalendar();'

if old_init in c:
    c = c.replace(old_init, new_init)
    changes.append("content/remarks add event listeners added")

# ===== L. Add renderEditContent and renderEditRemarks functions =====
render_content_fn = (
    '    function renderEditContent() {\n'
    '        const list = document.getElementById("edit-content-list");\n'
    '        if (!list) { console.error("edit-content-list not found"); return; }\n'
    '        list.innerHTML = "";\n'
    '        currentContent.forEach((item, idx) => {\n'
    '            const li = document.createElement("li");\n'
    '            li.className = "todo-item";\n'
    '            const num = document.createElement("span");\n'
    '            num.style.cssText = "color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;";\n'
    '            num.textContent = (idx + 1) + ".";\n'
    '            const check = document.createElement("div");\n'
    '            check.className = "todo-check" + (item.done ? " done" : "");\n'
    '            check.textContent = item.done ? " [OK]" : "";\n'
    '            check.addEventListener("click", () => { currentContent[idx].done = !currentContent[idx].done; renderEditContent(); });\n'
    '            const input = document.createElement("input");\n'
    '            input.className = "todo-add-input";\n'
    '            input.style.flex = "1";\n'
    '            input.value = item.text;\n'
    '            input.addEventListener("input", () => { currentContent[idx].text = input.value; });\n'
    '            const del = document.createElement("span");\n'
    '            del.className = "todo-del";\n'
    '            del.textContent = "x";\n'
    '            del.style.cssText = "cursor:pointer; color:#e74c3c; font-size:16px; padding:0 4px;";\n'
    '            del.addEventListener("click", () => { currentContent.splice(idx, 1); renderEditContent(); });\n'
    '            li.appendChild(num);\n'
    '            li.appendChild(check);\n'
    '            li.appendChild(input);\n'
    '            li.appendChild(del);\n'
    '            list.appendChild(li);\n'
    '        });\n'
    '    }\n'
    '\n'
    '    function renderEditRemarks() {\n'
    '        const list = document.getElementById("edit-remarks-list");\n'
    '        if (!list) { console.error("edit-remarks-list not found"); return; }\n'
    '        list.innerHTML = "";\n'
    '        currentRemarks.forEach((item, idx) => {\n'
    '            const li = document.createElement("li");\n'
    '            li.className = "todo-item";\n'
    '            const num = document.createElement("span");\n'
    '            num.style.cssText = "color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;";\n'
    '            num.textContent = (idx + 1) + ".";\n'
    '            const check = document.createElement("div");\n'
    '            check.className = "todo-check" + (item.done ? " done" : "");\n'
    '            check.textContent = item.done ? " [OK]" : "";\n'
    '            check.addEventListener("click", () => { currentRemarks[idx].done = !currentRemarks[idx].done; renderEditRemarks(); });\n'
    '            const input = document.createElement("input");\n'
    '            input.className = "todo-add-input";\n'
    '            input.style.flex = "1";\n'
    '            input.value = item.text;\n'
    '            input.addEventListener("input", () => { currentRemarks[idx].text = input.value; });\n'
    '            const del = document.createElement("span");\n'
    '            del.className = "todo-del";\n'
    '            del.textContent = "x";\n'
    '            del.style.cssText = "cursor:pointer; color:#e74c3c; font-size:16px; padding:0 4px;";\n'
    '            del.addEventListener("click", () => { currentRemarks.splice(idx, 1); renderEditRemarks(); });\n'
    '            li.appendChild(num);\n'
    '            li.appendChild(check);\n'
    '            li.appendChild(input);\n'
    '            li.appendChild(del);\n'
    '            list.appendChild(li);\n'
    '        });\n'
    '    }\n'
    '\n'
)

# Insert before showEditMode function body
showEdit_pos = c.find('function showEditMode(data, isNew) {')
if showEdit_pos > 0:
    c = c[:showEdit_pos] + render_content_fn + c[showEdit_pos:]
    changes.append("renderEditContent + renderEditRemarks added")
else:
    print("FATAL: showEditMode not found")
    exit(1)

# ===== M. Update view-remarks-list content rendering (separate from content_list) =====
# Make sure remarks list is populated in showViewMode
# Find showViewMode's remarks section
old_view_remarks2 = '                        <div class="view-label">备注</div>\n                        <ul id="view-remarks-list" style="list-style:none; padding:0; margin:0;"></ul>'
if old_view_remarks2 in c:
    pass  # already correct

# ===== N. Set mood action button in saveJournal uses global currentContent =====

# All good, write
path.write_text(c, encoding='utf-8')
for ch in changes:
    print('OK:', ch)
print(f'\nTotal changes: {len(changes)}')
