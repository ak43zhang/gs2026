from pathlib import Path
c = Path('src/gs2026/dashboard2/templates/profile.html').read_text(encoding='utf-8')

def chk(name, cond):
    print(f"{'OK' if cond else 'FAIL'}: {name}")

chk('j-content textarea gone', 'id="j-content"' not in c)
chk('j-remarks textarea gone', 'id="j-remarks"' not in c)
chk('edit-content-list exists', 'edit-content-list' in c)
chk('edit-remarks-list exists', 'edit-remarks-list' in c)
chk('view-content-list exists', 'view-content-list' in c)
chk('view-remarks-list exists', 'view-remarks-list' in c)
chk('renderEditContent exists', 'function renderEditContent()' in c)
chk('renderEditRemarks exists', 'function renderEditRemarks()' in c)
chk('parseContent exists', 'function parseContent(' in c)
chk('parseRemarks exists', 'function parseRemarks(' in c)
chk('contentToJson exists', 'function contentToJson(' in c)
chk('remarksToJson exists', 'function remarksToJson(' in c)
chk('save journal uses contentToJson(currentContent)', 'contentToJson(currentContent)' in c)
chk('save journal uses remarksToJson(currentRemarks)', 'remarksToJson(currentRemarks)' in c)
chk('no j-content getElementById', "getElementById('j-content')" not in c)
chk('no j-remarks getElementById', "getElementById('j-remarks')" not in c)
chk('content-add-btn listener', "getElementById('content-add-btn').addEventListener" in c)
chk('remarks-add-btn listener', "getElementById('remarks-add-btn').addEventListener" in c)
chk('saveContentOnly function', 'function saveContentOnly()' in c)

# check showEditMode uses currentContent/currentRemarks
chk('showEditMode sets currentContent', 'currentContent = parseContent' in c)
chk('showEditMode sets currentRemarks', 'currentRemarks = parseRemarks' in c)
chk('showEditMode calls renderEditContent', 'renderEditContent();' in c)
chk('showEditMode calls renderEditRemarks', 'renderEditRemarks();' in c)

# Check for stale references
for stale in ['j-content', 'j-remarks']:
    remaining = []
    idx = 0
    while True:
        idx = c.find(stale, idx)
        if idx == -1:
            break
        remaining.append(idx)
        idx += 1
    if remaining:
        print(f"WARNING: remaining '{stale}' references at positions: {remaining[:5]}")
    else:
        print(f"OK: no stale '{stale}' references")
