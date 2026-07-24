# 报告中心-软连接目录方案（v3）

## 思路

将 `F:\pyworkspace2026\gs2026\docs` 软连接到报告中心根目录 `G:\report\项目文档`，使其作为一个新的"报告分类"出现在现有报告中心UI中。后续其他目录同理，只需再建一个软连接。

---

## 现有报告中心结构

```
G:/report/                          ← ReportService.REPORT_ROOT
├── 书籍/ (2个文件)
├── 智能报告/ (23个文件)
├── 涨停板报告/ (4个文件)
├── 领域事件报告/ (3个文件)
└── 项目文档/                       ← 【新增软连接】→ F:\pyworkspace2026\gs2026\docs
    ├── 00-项目说明/
    ├── 01-需求与设计/
    ├── ...
    └── 99-附件/
```

## 现有限制 & 需要修改

| 限制 | 现状 | 修改 |
|------|------|------|
| 支持格式 | `.pdf`, `.epub`, `.html` | 添加 `.md`, `.docx`, `.sql`, `.txt` |
| 目录深度 | 只扫描1层 | 支持子目录浏览（递归导航） |
| 文件渲染 | pdf/epub | 复用已有 md-viewer.js、docx-viewer.js |

---

## 实施步骤

### 步骤1：创建目录联接（无需管理员权限）

```cmd
mklink /J "G:\report\项目文档" "F:\pyworkspace2026\gs2026\docs"
```

> Windows目录联接（Junction）不需要管理员权限，效果等同软连接。
> 后续添加新目录只需再执行一次 `mklink /J`。

### 步骤2：修改 report_service.py（2处）

**修改1**：扩展支持格式
```python
# 修改前
SUPPORTED_EXTENSIONS = ['.pdf', '.epub', '.html']

# 修改后
SUPPORTED_EXTENSIONS = ['.pdf', '.epub', '.html', '.md', '.docx', '.sql', '.txt']
```

**修改2**：`get_reports_by_type()` 支持子路径浏览
```python
def get_reports_by_type(self, report_type: str, sub_path: str = '') -> List[Dict]:
    """
    获取报告列表，支持子目录浏览
    
    Args:
        report_type: 顶层分类（目录名）
        sub_path: 子路径（如 '01-需求与设计/功能需求设计'）
    """
    target_dir = self.root / report_type
    if sub_path:
        target_dir = target_dir / sub_path
    
    if not target_dir.exists():
        return []
    
    items = []
    
    # 先列子目录
    for item in sorted(target_dir.iterdir()):
        if item.is_dir() and not item.name.startswith('.'):
            file_count = sum(1 for f in item.rglob('*') if f.is_file())
            items.append({
                "id": str(item.relative_to(self.root)),
                "name": item.name,
                "type": "directory",
                "count": file_count,
                "path": str(item.relative_to(self.root))
            })
    
    # 再列文件
    for item in sorted(target_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
            stat = item.stat()
            items.append({
                "id": str(item.relative_to(self.root)),
                "name": item.stem,
                "filename": item.name,
                "type": "file",
                "format": item.suffix.lower().replace('.', ''),
                "path": str(item.relative_to(self.root)),
                "relative_path": str(item.relative_to(self.root)),
                "size_formatted": self._format_size(stat.st_size),
                "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    
    return items
```

### 步骤3：修改 routes/report.py（1处）

添加 `sub_path` 参数支持：
```python
@report_bp.route('/list', methods=['GET'])
def get_reports():
    report_type = request.args.get('type', '')
    sub_path = request.args.get('path', '')  # 【新增】子路径
    reports = report_service.get_reports_by_type(report_type, sub_path)
    return jsonify({"success": True, "data": reports})
```

### 步骤4：修改前端 reports.html/report-page.js

- 文件列表中显示子目录（带文件夹图标📁）
- 点击子目录 → 传入 `path` 参数请求子目录内容
- 面包屑导航（点击可返回上级）
- .md文件 → 调用已有 md-viewer.js 渲染
- .docx文件 → 调用已有 docx-viewer.js 渲染

---

## 变更清单

| 操作 | 文件 | 改动量 |
|------|------|--------|
| **命令** | `mklink /J` | 1条命令 |
| **修改** | `services/report_service.py` | ~30行 |
| **修改** | `routes/report.py` | ~5行 |
| **修改** | 前端（报告列表+面包屑） | ~50行 |

---

## 后续扩展（只需1条命令）

```cmd
:: 添加新的文档目录
mklink /J "G:\report\研究笔记" "D:\研究笔记"
mklink /J "G:\report\会议纪要" "E:\会议\2026"
```

无需改代码，报告中心自动发现新目录。

---

**审核状态**: 待审核
