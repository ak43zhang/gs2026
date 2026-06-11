"""Check KB script for syntax issues"""
import re

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    lines = f.readlines()

# Extract KB script block
in_kb = False
kb_lines = []
start_line = 0
for i, line in enumerate(lines, 1):
    if '// ===== 知识库功能 =====' in line:
        in_kb = True
        start_line = i
    if in_kb:
        kb_lines.append((i, line))
        if '</script>' in line:
            break

print(f"KB script: lines {start_line} to {kb_lines[-1][0]}, {len(kb_lines)} lines")

# Check for HTML entities that shouldn't be in JS
problems = []
for lineno, line in kb_lines:
    # Check for & < > " (HTML entities in JS = bug)
    if '&' in line or '<' in line or '>' in line or '"' in line:
        problems.append((lineno, line.rstrip()[:120]))

if problems:
    print(f"\nWARNING: {len(problems)} lines with HTML entities in JS:")
    for lineno, text in problems:
        print(f"  {lineno}: {text}")
else:
    print("\nNo HTML entities in JS - OK")

# Also check if marked.js loading could block
for i, line in enumerate(lines, 1):
    if 'marked.min.js' in line:
        print(f"\nmarked.js at line {i}: {line.rstrip()[:120]}")
        # Check if it has async/defer
        if 'async' not in line and 'defer' not in line:
            print("  WARNING: No async/defer - if CDN fails, may block page")
