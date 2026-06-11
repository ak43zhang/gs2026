"""Fix line 2104 kbFilterTag onclick quote issue - exact match"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    lines = f.readlines()

line = lines[2103]

# Exact pattern from inspection:
# onclick="kbFilterTag('' + kbEsc(t) + '')"
# Replace with:
# data-kbtag="' + kbEsc(t) + '"

old = """onclick="kbFilterTag('' + kbEsc(t) + '')\""""
new = """data-kbtag="' + kbEsc(t) + '\""""

new_line = line.replace(old, new)

if new_line != line:
    lines[2103] = new_line
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Fixed successfully")
    print(f"New chars 290-370: {repr(new_line[290:370])}")
else:
    print("Pattern not matched")
    # Print the exact bytes
    start = line.index('onclick')
    end = start + 60
    print(f"Exact bytes: {repr(line[start:end])}")
