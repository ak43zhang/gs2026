"""Add kb page to profile.html"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    content = f.read()

# 1. Add kb page content before page-placeholders
kb_page_html = '''
            <!-- 知识库页面 -->
            <main class="profile-content" id="page-kb" style="display:none;padding:0;">
                <div style="display:flex;height:100%;overflow:hidden;">
                    <!-- 左侧列表 -->
                    <div style="width:300px;border-right:1px solid #e8e8e8;display:flex;flex-direction:column;background:#fff;">
                        <div style="padding:12px;border-bottom:1px solid #e8e8e8;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                                <span style="font-size:15px;font-weight:600;">📖 知识库</span>
                                <button onclick="kbNewEntry()" style="padding:3px 10px;border-radius:4px;border:1px solid #1890ff;background:#1890ff;color:#fff;cursor:pointer;font-size:12px;">+ 新建</button>
                            </div>
                            <input id="kb-search" placeholder="搜索标题或内容..." oninput="kbDebounceSearch()" style="width:100%;padding:5px 8px;border:1px solid #d9d9d9;border-radius:4px;font-size:12px;">
                            <div id="kb-tags" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;"></div>
                        </div>
                        <div id="kb-list" style="flex:1;overflow-y:auto;"></div>
                    </div>
                    <!-- 右侧内容 -->
                    <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
                        <div id="kb-toolbar" style="display:none;padding:8px 16px;border-bottom:1px solid #e8e8e8;background:#fff;display:flex;align-items:center;gap:8px;">
                            <button id="kb-btn-edit" onclick="kbToggleEdit()" style="padding:3px 10px;border-radius:4px;border:1px solid #d9d9d9;background:#fff;cursor:pointer;font-size:12px;">✏️ 编辑</button>
                            <button id="kb-btn-save" onclick="kbSaveEntry()" style="display:none;padding:3px 10px;border-radius:4px;border:1px solid #1890ff;background:#1890ff;color:#fff;cursor:pointer;font-size:12px;">💾 保存</button>
                            <button id="kb-btn-cancel" onclick="kbCancelEdit()" style="display:none;padding:3px 10px;border-radius:4px;border:1px solid #d9d9d9;background:#fff;cursor:pointer;font-size:12px;">取消</button>
                            <div style="flex:1;"></div>
                            <button id="kb-btn-delete" onclick="kbDeleteEntry()" style="padding:3px 10px;border-radius:4px;border:1px solid #ff4d4f;color:#ff4d4f;background:#fff;cursor:pointer;font-size:12px;">🗑️ 删除</button>
                        </div>
                        <div id="kb-content" style="flex:1;overflow-y:auto;padding:16px;">
                            <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#bbb;font-size:14px;">选择左侧条目查看，或点击 "+ 新建" 创建</div>
                        </div>
                    </div>
                </div>
            </main>

'''

marker = '            <!-- 占位内容区 -->'
if marker in content:
    content = content.replace(marker, kb_page_html + marker)
    print('[1] Added kb page HTML')
else:
    print('[1] Marker not found')

# 2. Add kb page hide + switch logic in sidebar navigation
old_hide = "document.getElementById('page-placeholders').style.display = 'none';\n            \n            // 【新增】门规主题切换"
new_hide = """var kbPage = document.getElementById('page-kb');
            if (kbPage) kbPage.style.display = 'none';
            document.getElementById('page-placeholders').style.display = 'none';
            
            // 【新增】门规主题切换"""

if old_hide in content:
    content = content.replace(old_hide, new_hide)
    print('[2] Added kb hide logic')
else:
    print('[2] Hide marker not found, trying alternative...')
    # Try with exact spacing from the file
    old_hide2 = "document.getElementById('page-placeholders').style.display = 'none';"
    # Find the first occurrence that's in the sidebar nav section
    idx = content.find("document.getElementById('page-placeholders').style.display = 'none';")
    if idx >= 0:
        content = content[:idx] + "var kbPage = document.getElementById('page-kb');\n            if (kbPage) kbPage.style.display = 'none';\n            " + content[idx:]
        print('[2b] Added kb hide logic (alt)')
    else:
        print('[2] Failed to add hide logic')

# 3. Add kb page show logic after rules
old_rules = """} else if (page === 'rules') {
                if (rulesPage) rulesPage.style.display = '';
                if (typeof refreshRulesPage === 'function') refreshRulesPage();
            } else if (page === 'journal') {"""

new_rules = """} else if (page === 'rules') {
                if (rulesPage) rulesPage.style.display = '';
                if (typeof refreshRulesPage === 'function') refreshRulesPage();
            } else if (page === 'kb') {
                var kbP = document.getElementById('page-kb');
                if (kbP) kbP.style.display = '';
                if (typeof kbInit === 'function' && !window._kbInited) { kbInit(); window._kbInited = true; }
            } else if (page === 'journal') {"""

if old_rules in content:
    content = content.replace(old_rules, new_rules)
    print('[3] Added kb switch logic')
else:
    print('[3] Rules marker not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
