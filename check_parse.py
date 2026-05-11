from pathlib import Path
c = Path('src/gs2026/dashboard2/templates/profile.html').read_text(encoding='utf-8')

# Check exact line numbers
script_start = c.find('<script>')
if script_start < 0:
    print("No <script> tag found!")
else:
    lines = c[script_start:].split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('function ') or stripped.startswith('var ') or stripped.startswith('let ') or stripped.startswith('const '):
            print(f"S-L{i}: {stripped[:100]}")
        if 'currentContent' in line or 'parseContent' in line or 'parseRemarks' in line:
            print(f"  R{i}: {stripped[:120]}")
