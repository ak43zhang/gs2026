"""Fix: Add tab buttons to buy-points-panel header"""
import re

filepath = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Check current state
has_tabs = 'bp-tab-btn' in content
has_switch = 'switchBpTab' in content
print(f"Current state: has_tabs={has_tabs}, has_switch={has_switch}")

if not has_tabs:
    # Find the h2 inside buy-points-panel and replace it
    # Pattern: the h2 line after buy-points-panel
    old_h2 = '''<h2 style="display:flex;align-items:center;justify-content:space-between;"><span style="display:flex;align-items:center;gap:6px;">\U0001f3af \u8cb7\u70b9\u5019\u9009</span>
                        <span class="bp-settings-btn" onclick="toggleBpEditor()" title="\u6761\u4ef6\u8bbe\u7f6e">\u2699</span>
                </h2>'''
    
    # Try to find any h2 pattern near buy-points-panel
    idx = content.find('buy-points-panel')
    if idx < 0:
        print("ERROR: buy-points-panel not found!")
        exit(1)
    
    # Find the <h2 after this
    h2_start = content.find('<h2', idx)
    h2_end = content.find('</h2>', h2_start) + len('</h2>')
    
    old_header = content[h2_start:h2_end]
    print(f"Found h2 at chars {h2_start}-{h2_end}")
    print(f"Old header (first 100): {old_header[:100]}")
    
    new_header = '''<h2 style="display:flex;align-items:center;justify-content:space-between;">
                    <span style="display:flex;align-items:center;gap:0;">
                        <span id="bp-tab-btn" onclick="switchBpTab('bp')" style="cursor:pointer;padding:2px 8px;border-radius:4px 0 0 4px;border:1px solid #667eea;background:#667eea;color:#fff;font-size:12px;">\U0001f3af \u8cb7\u70b9\u5019\u9009</span>
                        <span id="qs-tab-btn" onclick="switchBpTab('qs')" style="cursor:pointer;padding:2px 8px;border-radius:0 4px 4px 0;border:1px solid #667eea;background:#fff;color:#667eea;font-size:12px;">\U0001f4ca \u91cf\u5316\u9009\u503a</span>
                    </span>
                    <span class="bp-settings-btn" onclick="toggleBpEditor()" title="\u6761\u4ef6\u8bbe\u7f6e">\u2699</span>
                </h2>'''
    
    content = content[:h2_start] + new_header + content[h2_end:]
    print("Replaced h2 with tabbed version")

# Also ensure switchBpTab function exists
if 'function switchBpTab' not in content:
    # Insert before the quantscreen toggle function
    insert_point = content.find('function toggleQuantScreen')
    if insert_point < 0:
        insert_point = content.find('// ==================== ')
    
    switch_fn = '''
        function switchBpTab(tab) {
            var bpList = document.getElementById('bp-list');
            var qsSection = document.getElementById('quant-screen-section');
            var bpBtn = document.getElementById('bp-tab-btn');
            var qsBtn = document.getElementById('qs-tab-btn');
            if (tab === 'bp') {
                if (bpList) bpList.style.display = '';
                if (qsSection) qsSection.style.display = 'none';
                if (bpBtn) { bpBtn.style.background = '#667eea'; bpBtn.style.color = '#fff'; }
                if (qsBtn) { qsBtn.style.background = '#fff'; qsBtn.style.color = '#667eea'; }
            } else {
                if (bpList) bpList.style.display = 'none';
                if (qsSection) qsSection.style.display = '';
                if (qsBtn) { qsBtn.style.background = '#667eea'; qsBtn.style.color = '#fff'; }
                if (bpBtn) { bpBtn.style.background = '#fff'; bpBtn.style.color = '#667eea'; }
                renderQsSchemes();
            }
        }

'''
    content = content[:insert_point] + switch_fn + content[insert_point:]
    print("Inserted switchBpTab function")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    verify = f.read()
print(f"\nVerification: bp-tab-btn={'bp-tab-btn' in verify}, switchBpTab={'switchBpTab' in verify}")
