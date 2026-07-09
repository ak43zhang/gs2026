"""Direct fix: replace the h2 in buy-points-panel with tabbed version"""
filepath = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the h2 tag after buy-points-panel
idx = content.find('buy-points-panel')
h2_start = content.find('<h2', idx)
h2_end = content.find('</h2>', h2_start) + 5  # include </h2>

old_h2 = content[h2_start:h2_end]

# New tabbed header
new_h2 = '<h2 style="display:flex;align-items:center;justify-content:space-between;"><span style="display:flex;align-items:center;gap:0;"><span id="bp-tab-btn" onclick="switchBpTab(\'bp\')" style="cursor:pointer;padding:2px 8px;border-radius:4px 0 0 4px;border:1px solid #667eea;background:#667eea;color:#fff;font-size:12px;">\U0001f3af \u8cb7\u70b9\u5019\u9009</span><span id="qs-tab-btn" onclick="switchBpTab(\'qs\')" style="cursor:pointer;padding:2px 8px;border-radius:0 4px 4px 0;border:1px solid #667eea;background:#fff;color:#667eea;font-size:12px;">\U0001f4ca \u91cf\u5316\u9009\u503a</span></span><span class="bp-settings-btn" onclick="toggleBpEditor()" title="\u6761\u4ef6\u8bbe\u7f6e">\u2699</span></h2>'

if 'bp-tab-btn' in old_h2:
    with open(r'F:\pyworkspace2026\gs2026\temp\fix_result.txt', 'w') as f:
        f.write("ALREADY_HAS_TABS\n")
        f.write(f"h2 length: {len(old_h2)}\n")
        f.write(f"first 200: {old_h2[:200]}\n")
else:
    content = content[:h2_start] + new_h2 + content[h2_end:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    with open(r'F:\pyworkspace2026\gs2026\temp\fix_result.txt', 'w') as f:
        f.write("FIXED\n")
        f.write(f"old h2 (first 200): {old_h2[:200]}\n")

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    v = f.read()
with open(r'F:\pyworkspace2026\gs2026\temp\fix_result.txt', 'a') as f:
    f.write(f"\nVERIFY: bp-tab-btn={'bp-tab-btn' in v}\n")
    f.write(f"VERIFY: switchBpTab={'switchBpTab' in v}\n")
