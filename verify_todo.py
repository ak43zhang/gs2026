from pathlib import Path
c = Path('src/gs2026/dashboard2/templates/profile.html').read_text(encoding='utf-8')
checks = {
    'j-content textarea GONE': 'id="j-content"' not in c,
    'j-remarks textarea GONE': 'id="j-remarks"' not in c,
    'edit-content-list EXISTS': 'edit-content-list' in c,
    'edit-remarks-list EXISTS': 'edit-remarks-list' in c,
    'renderEditContent fn': 'function renderEditContent()' in c,
    'renderEditRemarks fn': 'function renderEditRemarks()' in c,
    'parseContent fn': 'function parseContent(' in c,
    'parseRemarks fn': 'function parseRemarks(' in c,
    'contentToJson fn': 'function contentToJson(' in c,
    'remarksToJson fn': 'function remarksToJson(' in c,
    'content-add-btn listener': 'content-add-btn' in c,
    'remarks-add-btn listener': 'remarks-add-btn' in c,
    'saveJournal uses contentToJson': 'contentToJson(currentContent)' in c,
    'saveJournal uses remarksToJson': 'remarksToJson(currentRemarks)' in c,
}
all_ok = True
for k, v in checks.items():
    status = 'OK' if v else 'FAIL'
    if not v:
        all_ok = False
    print(f'{status}: {k}')
print(f'\nAll checks passed: {all_ok}')
