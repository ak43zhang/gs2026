# -*- coding: utf-8 -*-
"""Clean fix: replace h2 in buy-points-panel with tab buttons + add JS function"""

filepath = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Find h2 after buy-points-panel
idx = content.find('buy-points-panel')
h2_start = content.find('<h2', idx)
h2_end = content.find('</h2>', h2_start) + 5

# Build new h2 with tab buttons using actual characters
bp_label = '\U0001f3af \u4e70\u70b9\u5019\u9009'  # 🎯 买点候选
qs_label = '\U0001f4ca \u91cf\u5316\u9009\u503a'  # 📊 量化选债
gear = '\u2699'  # ⚙
settings_title = '\u6761\u4ef6\u8bbe\u7f6e'  # 条件设置

new_h2 = f'''<h2 style="display:flex;align-items:center;justify-content:space-between;">
                    <span style="display:flex;align-items:center;gap:0;">
                        <span id="bp-tab-btn" onclick="switchBpTab('bp')" style="cursor:pointer;padding:2px 8px;border-radius:4px 0 0 4px;border:1px solid #667eea;background:#667eea;color:#fff;font-size:12px;">{bp_label}</span>
                        <span id="qs-tab-btn" onclick="switchBpTab('qs')" style="cursor:pointer;padding:2px 8px;border-radius:0 4px 4px 0;border:1px solid #667eea;background:#fff;color:#667eea;font-size:12px;">{qs_label}</span>
                    </span>
                    <span class="bp-settings-btn" onclick="toggleBpEditor()" title="{settings_title}">{gear}</span>
                </h2>'''

content = content[:h2_start] + new_h2 + content[h2_end:]

# Add switchBpTab function if not present
if 'function switchBpTab' not in content:
    marker = 'function toggleQuantScreen'
    ins_idx = content.find(marker)
    if ins_idx > 0:
        fn = """function switchBpTab(tab) {
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

        """
        content = content[:ins_idx] + fn + content[ins_idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    v = f.read()

with open(r'F:\pyworkspace2026\gs2026\temp\fix_verify.txt', 'w') as f:
    f.write(f"bp-tab-btn: {v.count('bp-tab-btn')}\n")
    f.write(f"switchBpTab: {v.count('switchBpTab')}\n")
    f.write(f"qs-tab-btn: {v.count('qs-tab-btn')}\n")
