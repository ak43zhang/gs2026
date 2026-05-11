"""Move parseContent/parseRemarks from after </html> to inside <script> block"""
from pathlib import Path

path = Path('src/gs2026/dashboard2/templates/profile.html')
c = path.read_text(encoding='utf-8')

# 1. Find and extract functions that are after </html>
html_end = c.find('</html>')
after_html = c[html_end + len('</html>'):]
print(f"Content after </html>: {len(after_html)} chars")
print(repr(after_html[:200]))

# 2. Remove everything after </html>
c = c[:html_end + len('</html>')].rstrip() + '\n'

# 3. Extract the function definitions
funcs = after_html.strip()
print(f"\nFunctions to move:\n{funcs[:300]}...")

# 4. Insert them right after todosToJson
insert_marker = '    function todosToJson(todos) { return JSON.stringify(todos); }'
if insert_marker in c:
    c = c.replace(insert_marker, insert_marker + '\n\n' + funcs + '\n', 1)
    print("\nOK: Moved functions after todosToJson")
else:
    print("FAIL: todosToJson marker not found")
    exit(1)

# 5. Verify
print("\nVerification:")
print("  parseContent in script:", 'function parseContent(' in c[:c.find('</html>')])
print("  parseRemarks in script:", 'function parseRemarks(' in c[:c.find('</html>')])
print("  contentToJson in script:", 'function contentToJson(' in c[:c.find('</html>')])
print("  remarksToJson in script:", 'function remarksToJson(' in c[:c.find('</html>')])
print("  nothing after </html>:", c[c.find('</html>') + len('</html>'):].strip() == '')

path.write_text(c, encoding='utf-8')
print("\nDone!")
