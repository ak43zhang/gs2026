"""Add missing saveContentOnly function"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

# Check if saveContentOnly exists
if 'function saveContentOnly()' in c:
    print('SKIP: saveContentOnly already exists')
    exit(0)

# Check if it's referenced
if 'saveContentOnly()' not in c:
    print('SKIP: saveContentOnly not referenced anywhere')
    exit(0)

# Add the function before the // init comment
fn = (
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
    '                mood: currentViewData ? currentViewData.mood : ""\n'
    '            })\n'
    '        }).then(r => r.json()).then(() => {\n'
    '            if (currentViewData) currentViewData.content = contentToJson(currentContent);\n'
    '        });\n'
    '    }\n\n'
)

marker = '    // content add button + enter key'
if marker in c:
    c = c.replace(marker, fn + marker, 1)
    print('OK: Added saveContentOnly function')
else:
    marker2 = '    // init\n    initCalendar();'
    c = c.replace(marker2, fn + marker2, 1)
    print('OK: Added saveContentOnly function (before init)')

path.write_text(c, encoding='utf-8')
