from pathlib import Path
c = Path('src/gs2026/dashboard2/templates/profile.html').read_text(encoding='utf-8')
lines = c.split('\n')
for i, line in enumerate(lines):
    if 'sidebar' in line.lower() and 'addevent' in line.lower():
        print(f'L{i+1}: {line.rstrip()[:120]}')
print('---')
for i, line in enumerate(lines):
    if 'querySelectorAll' in line and 'sidebar' in line:
        print(f'L{i+1}: {line.rstrip()[:120]}')
        # show context
        for j in range(i, min(i+10, len(lines))):
            print(f'  L{j+1}: {lines[j].rstrip()[:120]}')
            if j > 5: break
print('---')
# Look for showPage function
for i, line in enumerate(lines):
    if 'showPage' in line:
        print(f'L{i+1}: {line.rstrip()[:120]}')
