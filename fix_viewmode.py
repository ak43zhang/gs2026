"""Fix showViewMode to render content/remarks as lists"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')
changes = []

# 1. Replace view-content rendering in showViewMode
old_view = "        document.getElementById('view-content').textContent = data.content || '';\n        document.getElementById('view-remarks').textContent = data.remarks || '';"

new_view = (
    "        // content items as list\n"
    "        currentContent = parseContent(data.content || '');\n"
    "        const contentList = document.getElementById('view-content') || document.getElementById('view-content-list');\n"
    "        if (contentList) {\n"
    "            contentList.innerHTML = '';\n"
    "            if (currentContent.length > 0) {\n"
    "                currentContent.forEach((item, idx) => {\n"
    "                    const li = document.createElement('li');\n"
    "                    li.className = 'todo-item';\n"
    "                    const num = document.createElement('span');\n"
    "                    num.style.cssText = 'color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;';\n"
    "                    num.textContent = (idx + 1) + '.';\n"
    "                    const text = document.createElement('span');\n"
    "                    text.className = 'todo-text';\n"
    "                    text.textContent = item.text;\n"
    "                    li.appendChild(num);\n"
    "                    li.appendChild(text);\n"
    "                    contentList.appendChild(li);\n"
    "                });\n"
    "            } else {\n"
    "                contentList.innerHTML = '<li style=\"color:#aaa;\">暂无内容</li>';\n"
    "            }\n"
    "        }\n"
    "\n"
    "        // remarks items as list\n"
    "        currentRemarks = parseRemarks(data.remarks || '');\n"
    "        const remarksList = document.getElementById('view-remarks') || document.getElementById('view-remarks-list');\n"
    "        if (remarksList) {\n"
    "            remarksList.innerHTML = '';\n"
    "            if (currentRemarks.length > 0) {\n"
    "                currentRemarks.forEach((item, idx) => {\n"
    "                    const li = document.createElement('li');\n"
    "                    li.className = 'todo-item';\n"
    "                    const num = document.createElement('span');\n"
    "                    num.style.cssText = 'color:#8a7e6e; font-size:13px; min-width:24px; flex-shrink:0;';\n"
    "                    num.textContent = (idx + 1) + '.';\n"
    "                    const text = document.createElement('span');\n"
    "                    text.className = 'todo-text';\n"
    "                    text.textContent = item.text;\n"
    "                    li.appendChild(num);\n"
    "                    li.appendChild(text);\n"
    "                    remarksList.appendChild(li);\n"
    "                });\n"
    "            } else {\n"
    "                remarksList.innerHTML = '<li style=\"color:#aaa;\">暂无备注</li>';\n"
    "            }\n"
    "        }"
)

if old_view in c:
    c = c.replace(old_view, new_view)
    changes.append("showViewMode: content/remarks rendered as lists")
else:
    print("FAIL: old view pattern not found")
    # Try finding them separately
    old_content_view = "document.getElementById('view-content').textContent = data.content || '';"
    old_remarks_view = "document.getElementById('view-remarks').textContent = data.remarks || '';"
    if old_content_view in c:
        print("  Found content view line separately")
    if old_remarks_view in c:
        print("  Found remarks view line separately")
    exit(1)

# 2. Fix the edit button data capture to use currentContent/currentRemarks
old_edit_btn = "            content: document.getElementById('view-content').textContent,"
new_edit_btn = "            content: contentToJson(currentContent),"
if old_edit_btn in c:
    c = c.replace(old_edit_btn, new_edit_btn)
    changes.append("edit button: content from currentContent")

old_edit_btn2 = "            remarks: document.getElementById('view-remarks').textContent,"
new_edit_btn2 = "            remarks: remarksToJson(currentRemarks),"
if old_edit_btn2 in c:
    c = c.replace(old_edit_btn2, new_edit_btn2)
    changes.append("edit button: remarks from currentRemarks")

# 3. Fix toggleTodoInView to use contentToJson/remarksToJson for save
old_toggle_save = "                    content: currentViewData.content || '',"
new_toggle_save = "                    content: contentToJson(currentContent),"
if old_toggle_save in c:
    c = c.replace(old_toggle_save, new_toggle_save)
    changes.append("toggleTodoInView: content as JSON")

old_toggle_save2 = "                    remarks: currentViewData.remarks || '',"
new_toggle_save2 = "                    remarks: remarksToJson(currentRemarks),"
if old_toggle_save2 in c:
    c = c.replace(old_toggle_save2, new_toggle_save2)
    changes.append("toggleTodoInView: remarks as JSON")

path.write_text(c, encoding='utf-8')
for ch in changes:
    print('OK:', ch)
print(f'\nTotal: {len(changes)} changes')
