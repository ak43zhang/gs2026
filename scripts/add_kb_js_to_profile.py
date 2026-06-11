"""Add KB JavaScript to profile.html before </body>"""

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', encoding='utf-8') as f:
    content = f.read()

kb_js = '''
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
// ===== 知识库功能 =====
var _kbEntries = [];
var _kbCurrentId = null;
var _kbIsEditing = false;
var _kbSearchTimer = null;
var _kbActiveTag = '';

function kbInit() {
    kbLoadTags();
    kbLoadEntries();
}

function kbDebounceSearch() {
    if (_kbSearchTimer) clearTimeout(_kbSearchTimer);
    _kbSearchTimer = setTimeout(kbLoadEntries, 300);
}

async function kbLoadEntries() {
    var q = document.getElementById('kb-search').value.trim();
    var url = '/kb/api/entries?page_size=100';
    if (q) url += '&q=' + encodeURIComponent(q);
    if (_kbActiveTag) url += '&tag=' + encodeURIComponent(_kbActiveTag);
    try {
        var r = await (await fetch(url)).json();
        if (r.success) { _kbEntries = r.items; kbRenderList(); }
    } catch(e) { console.error('[KB]', e); }
}

async function kbLoadTags() {
    try {
        var r = await (await fetch('/kb/api/tags')).json();
        if (r.success) kbRenderTags(r.tags);
    } catch(e) {}
}

function kbRenderList() {
    var el = document.getElementById('kb-list');
    if (!_kbEntries.length) {
        el.innerHTML = '<div style="padding:20px;text-align:center;color:#bbb;">暂无条目</div>';
        return;
    }
    el.innerHTML = _kbEntries.map(function(e) {
        return '<div class="kb-list-item' + (_kbCurrentId === e.id ? ' kb-active' : '') + '" onclick="kbSelectEntry(' + e.id + ')">' +
            '<div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + kbEsc(e.title) + '</div>' +
            '<div style="font-size:11px;color:#999;">' + e.updated_at.slice(0,16) + '</div>' +
            (e.tags.length ? '<div style="margin-top:2px;">' + e.tags.map(function(t){return '<span style="display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;background:#f0f0f0;color:#666;margin-right:3px;">'+kbEsc(t)+'</span>';}).join('') + '</div>' : '') +
        '</div>';
    }).join('');
}

function kbRenderTags(tags) {
    var el = document.getElementById('kb-tags');
    el.innerHTML = tags.map(function(t) {
        return '<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;cursor:pointer;border:1px solid ' + (_kbActiveTag === t ? '#1890ff' : '#d9d9d9') + ';background:' + (_kbActiveTag === t ? '#1890ff' : '#fafafa') + ';color:' + (_kbActiveTag === t ? '#fff' : '#333') + ';" onclick="kbFilterTag(\'' + kbEsc(t) + '\')">' + kbEsc(t) + '</span>';
    }).join('');
}

function kbFilterTag(tag) {
    _kbActiveTag = _kbActiveTag === tag ? '' : tag;
    kbLoadTags();
    kbLoadEntries();
}

async function kbSelectEntry(id) {
    _kbCurrentId = id;
    _kbIsEditing = false;
    kbRenderList();
    try {
        var r = await (await fetch('/kb/api/entries/' + id)).json();
        if (r.success) kbRenderView(r.data);
    } catch(e) { console.error('[KB]', e); }
}

function kbRenderView(data) {
    var toolbar = document.getElementById('kb-toolbar');
    toolbar.style.display = 'flex';
    document.getElementById('kb-btn-edit').style.display = '';
    document.getElementById('kb-btn-save').style.display = 'none';
    document.getElementById('kb-btn-cancel').style.display = 'none';
    document.getElementById('kb-btn-delete').style.display = '';
    
    var tagsHtml = data.tags.length ? '<div style="margin-bottom:12px;">' + data.tags.map(function(t){return '<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:#f0f5ff;color:#1890ff;margin-right:4px;">'+kbEsc(t)+'</span>';}).join('') + '</div>' : '';
    
    var contentHtml = '';
    try { contentHtml = marked.parse(data.content || ''); } catch(e) { contentHtml = '<pre>' + kbEsc(data.content || '') + '</pre>'; }
    
    document.getElementById('kb-content').innerHTML =
        '<div style="font-size:20px;font-weight:700;margin-bottom:8px;">' + kbEsc(data.title) + '</div>' +
        '<div style="font-size:12px;color:#999;margin-bottom:4px;">创建: ' + data.created_at.slice(0,16) + ' | 更新: ' + data.updated_at.slice(0,16) + '</div>' +
        tagsHtml +
        '<div style="margin-top:12px;line-height:1.8;">' + contentHtml + '</div>';
    
    document.getElementById('kb-content')._data = data;
}

function kbToggleEdit() {
    var data = document.getElementById('kb-content')._data;
    if (!data) return;
    _kbIsEditing = true;
    document.getElementById('kb-btn-edit').style.display = 'none';
    document.getElementById('kb-btn-save').style.display = '';
    document.getElementById('kb-btn-cancel').style.display = '';
    document.getElementById('kb-btn-delete').style.display = 'none';
    
    document.getElementById('kb-content').innerHTML =
        '<div style="display:flex;flex-direction:column;height:100%;">' +
        '<input id="kb-edit-title" value="' + kbEsc(data.title) + '" placeholder="标题" style="width:100%;padding:8px 12px;border:1px solid #d9d9d9;border-radius:4px;font-size:16px;font-weight:600;margin-bottom:8px;">' +
        '<input id="kb-edit-tags" value="' + data.tags.join(',') + '" placeholder="标签（逗号分隔）" style="width:100%;padding:6px 12px;border:1px solid #d9d9d9;border-radius:4px;font-size:12px;margin-bottom:8px;">' +
        '<textarea id="kb-edit-content" placeholder="正文（支持Markdown）" style="flex:1;width:100%;padding:12px;border:1px solid #d9d9d9;border-radius:4px;font-family:Consolas,monospace;font-size:13px;resize:none;line-height:1.6;">' + kbEsc(data.content || '') + '</textarea>' +
        '</div>';
    document.getElementById('kb-edit-title').focus();
}

function kbCancelEdit() {
    _kbIsEditing = false;
    var data = document.getElementById('kb-content')._data;
    if (data) {
        kbRenderView(data);
    } else {
        // 新建模式取消 → 恢复空状态
        document.getElementById('kb-toolbar').style.display = 'none';
        document.getElementById('kb-content').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#bbb;font-size:14px;">选择左侧条目查看，或点击 "+ 新建" 创建</div>';
        _kbCurrentId = null;
        kbRenderList();
    }
}

function kbNewEntry() {
    _kbCurrentId = null;
    _kbIsEditing = true;
    document.getElementById('kb-content')._data = null;
    kbRenderList();
    
    var toolbar = document.getElementById('kb-toolbar');
    toolbar.style.display = 'flex';
    document.getElementById('kb-btn-edit').style.display = 'none';
    document.getElementById('kb-btn-save').style.display = '';
    document.getElementById('kb-btn-cancel').style.display = '';
    document.getElementById('kb-btn-delete').style.display = 'none';
    
    document.getElementById('kb-content').innerHTML =
        '<div style="display:flex;flex-direction:column;height:100%;">' +
        '<input id="kb-edit-title" placeholder="标题" autofocus style="width:100%;padding:8px 12px;border:1px solid #d9d9d9;border-radius:4px;font-size:16px;font-weight:600;margin-bottom:8px;">' +
        '<input id="kb-edit-tags" placeholder="标签（逗号分隔，如：错误修复,MySQL）" style="width:100%;padding:6px 12px;border:1px solid #d9d9d9;border-radius:4px;font-size:12px;margin-bottom:8px;">' +
        '<textarea id="kb-edit-content" placeholder="正文（支持Markdown）" style="flex:1;width:100%;padding:12px;border:1px solid #d9d9d9;border-radius:4px;font-family:Consolas,monospace;font-size:13px;resize:none;line-height:1.6;"></textarea>' +
        '</div>';
    document.getElementById('kb-edit-title').focus();
}

async function kbSaveEntry() {
    var title = document.getElementById('kb-edit-title').value.trim();
    var content = document.getElementById('kb-edit-content').value;
    var tagsStr = document.getElementById('kb-edit-tags').value;
    var tags = tagsStr.split(',').map(function(t){return t.trim();}).filter(Boolean);
    
    if (!title) { alert('标题不能为空'); return; }
    
    try {
        var r;
        if (_kbCurrentId) {
            r = await fetch('/kb/api/entries/' + _kbCurrentId, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title, content: content, tags: tags})
            });
        } else {
            r = await fetch('/kb/api/entries', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title, content: content, tags: tags})
            });
        }
        var data = await r.json();
        if (data.success) {
            if (!_kbCurrentId && data.id) _kbCurrentId = data.id;
            _kbIsEditing = false;
            kbLoadTags();
            await kbLoadEntries();
            if (_kbCurrentId) kbSelectEntry(_kbCurrentId);
        } else { alert(data.message || '保存失败'); }
    } catch(e) { alert('网络错误: ' + e); }
}

async function kbDeleteEntry() {
    if (!_kbCurrentId) return;
    if (!confirm('确定删除该条目？')) return;
    try {
        var r = await fetch('/kb/api/entries/' + _kbCurrentId, {method: 'DELETE'});
        var data = await r.json();
        if (data.success) {
            _kbCurrentId = null;
            _kbIsEditing = false;
            document.getElementById('kb-toolbar').style.display = 'none';
            document.getElementById('kb-content').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#bbb;">已删除</div>';
            kbLoadTags();
            kbLoadEntries();
        }
    } catch(e) { alert('删除失败: ' + e); }
}

function kbEsc(s) {
    if (!s) return '';
    return s.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"');
}
</script>
<style>
.kb-list-item { padding:10px 12px; border-bottom:1px solid #f0f0f0; cursor:pointer; }
.kb-list-item:hover { background:#f5f7fa; }
.kb-list-item.kb-active { background:#e6f7ff; border-left:3px solid #1890ff; }
</style>
'''

marker = '</body>'
if marker in content:
    content = content.replace(marker, kb_js + marker)
    print('KB JS added successfully')
else:
    print('Marker not found')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\profile.html', 'w', encoding='utf-8') as f:
    f.write(content)
