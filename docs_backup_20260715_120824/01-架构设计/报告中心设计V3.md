# 报表中心设计方案 V3

## 1. 需求概述

### 1.1 功能目标
- 支持多种文档格式（PDF、Word、Excel、Markdown、HTML、TXT、**EPUB**）
- 报告在指定目录保存，前端可查看和阅读
- 支持语音播报功能（TTS）
- 多种报告类型（涨停报告、领域事件报告等，可扩展）
- 所有报告按时间倒序排列
- 暂不支持下载功能

### 1.2 支持文档格式
| 格式 | 扩展名 | 预览方式 | 语音播报 |
|------|--------|----------|----------|
| PDF | .pdf | pdf.js / 浏览器原生 | ✅ |
| Word | .docx | mammoth.js 转 HTML | ✅ |
| Excel | .xlsx | SheetJS / 表格渲染 | ⚠️ 摘要 |
| Markdown | .md | marked.js 渲染 | ✅ |
| HTML | .html | iframe 直接显示 | ✅ |
| 文本 | .txt | 纯文本显示 | ✅ |
| **EPUB** | **.epub** | **epub.js 渲染** | **✅** |

---

## 2. 数据库设计（统一前缀 report_）

### 2.1 报告元数据表（reports）
```sql
CREATE TABLE reports (
    report_id               INT PRIMARY KEY AUTO_INCREMENT,
    report_type             VARCHAR(50) NOT NULL,          -- 报告类型
    report_name             VARCHAR(255) NOT NULL,         -- 报告名称
    report_date             DATE NOT NULL,                 -- 报告日期
    report_file_path        VARCHAR(500) NOT NULL,         -- 文件路径
    report_file_format      VARCHAR(20) NOT NULL,          -- 文件格式
    report_file_size        BIGINT,                        -- 文件大小(字节)
    report_page_count       INT,                           -- 页数/段落数
    report_content_text     LONGTEXT,                      -- 纯文本内容（TTS用）
    report_tts_status       VARCHAR(20) DEFAULT 'pending', -- 语音状态
    report_tts_duration     INT,                           -- 语音时长(秒)
    report_tts_audio_path   VARCHAR(500),                  -- 语音文件路径
    report_params           JSON,                          -- 生成参数
    report_status           VARCHAR(20) DEFAULT 'completed',
    report_created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    report_updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_report_type_date (report_type, report_date),
    INDEX idx_report_format (report_file_format),
    INDEX idx_report_date (report_date),
    FULLTEXT INDEX idx_report_content (report_content_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.2 报告类型配置表（report_types）
```sql
CREATE TABLE report_types (
    report_type_id          INT PRIMARY KEY AUTO_INCREMENT,
    report_type_code        VARCHAR(50) UNIQUE NOT NULL,
    report_type_name        VARCHAR(100) NOT NULL,
    report_type_icon        VARCHAR(50),
    report_type_description TEXT,
    report_type_output_dir  VARCHAR(200) NOT NULL,
    report_type_default_format VARCHAR(20) DEFAULT 'pdf',
    report_type_supported_formats JSON,
    report_type_is_active   BOOLEAN DEFAULT TRUE,
    report_type_sort_order  INT DEFAULT 0,
    report_type_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始化数据
INSERT INTO report_types (
    report_type_code, report_type_name, report_type_icon, 
    report_type_output_dir, report_type_default_format, 
    report_type_supported_formats
) VALUES
('zt_report', '涨停报告', '📈', 'zt_report', 'pdf', 
 '["pdf", "epub", "md", "html"]'),
('event_report', '领域事件报告', '📰', 'event_report', 'pdf', 
 '["pdf", "epub", "md", "docx"]'),
('data_report', '数据报表', '📊', 'data_report', 'xlsx', 
 '["xlsx", "pdf", "epub", "html"]');
```

### 2.3 报告生成任务表（report_tasks）
```sql
CREATE TABLE report_tasks (
    report_task_id          VARCHAR(50) PRIMARY KEY,
    report_type             VARCHAR(50) NOT NULL,
    report_date             DATE NOT NULL,
    report_format           VARCHAR(20),
    report_task_status      VARCHAR(20) DEFAULT 'pending', -- pending/running/completed/failed
    report_task_progress    INT DEFAULT 0,
    report_task_message     TEXT,
    report_task_params      JSON,
    report_task_result_id   INT,                           -- 关联 reports.report_id
    report_task_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    report_task_updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_report_task_status (report_task_status),
    INDEX idx_report_task_type_date (report_type, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 3. API 设计（统一前缀）

### 3.1 报告管理接口
```python
# GET /api/reports/types
{
    "success": true,
    "data": [
        {
            "report_type_code": "zt_report",
            "report_type_name": "涨停报告",
            "report_type_icon": "📈",
            "report_count": 128,
            "report_type_default_format": "pdf",
            "report_type_supported_formats": ["pdf", "epub", "md", "html"]
        }
    ]
}

# GET /api/reports/list?type=zt_report&format=epub&page=1&pageSize=20
{
    "success": true,
    "data": {
        "report_total": 128,
        "report_page": 1,
        "report_page_size": 20,
        "report_list": [
            {
                "report_id": 1,
                "report_type": "zt_report",
                "report_name": "涨停报告_20260402",
                "report_date": "2026-04-02",
                "report_file_path": "/output/zt_report/2026/04/涨停报告_20260402.epub",
                "report_file_format": "epub",
                "report_file_size": 2048576,
                "report_page_count": 15,
                "report_tts_status": "ready",
                "report_tts_duration": 180,
                "report_created_at": "2026-04-02 18:30:00"
            }
        ]
    }
}

# GET /api/reports/{report_id}
{
    "success": true,
    "data": {
        "report_id": 1,
        "report_name": "涨停报告_20260402",
        "report_file_format": "epub",
        "report_view_url": "/api/reports/file/1/view",
        "report_content_text": "...报告纯文本内容...",
        "report_tts_audio_url": "/api/reports/1/tts/audio"
    }
}

# GET /api/reports/file/{report_id}/view
# 根据格式返回不同内容

# POST /api/reports/{report_id}/tts/generate
{
    "report_tts_voice": "zh-CN-XiaoxiaoNeural",
    "report_tts_speed": 1.0
}

# GET /api/reports/{report_id}/tts/status
{
    "success": true,
    "data": {
        "report_tts_status": "completed",
        "report_tts_progress": 100,
        "report_tts_audio_url": "/api/reports/1/tts/audio",
        "report_tts_duration": 180
    }
}

# GET /api/reports/{report_id}/tts/audio
# 返回 MP3 音频流

# POST /api/reports/generate
{
    "report_type": "zt_report",
    "report_date": "2026-04-03",
    "report_format": "epub",
    "report_params": {}
}
# 返回: {"success": true, "report_task_id": "zt_20260403_abc123"}

# GET /api/reports/tasks/{report_task_id}/status
{
    "success": true,
    "data": {
        "report_task_id": "zt_20260403_abc123",
        "report_task_status": "running",
        "report_task_progress": 65,
        "report_task_message": "正在生成 EPUB..."
    }
}

# DELETE /api/reports/{report_id}
# 删除报告（同时删除关联文件和语音）
```

---

## 4. EPUB 支持设计

### 4.1 EPUB 导出器
```python
# exporters/epub_exporter.py
class EPUBExporter(ReportExporter):
    """EPUB 导出器"""
    format = 'epub'
    
    def export(self, data: dict, output_path: str) -> str:
        """生成 EPUB 文件"""
        from ebooklib import epub
        
        book = epub.EpubBook()
        book.set_identifier(f"report_{data['id']}")
        book.set_title(data['title'])
        book.set_language('zh-CN')
        
        # 添加章节
        chapter = epub.EpubHtml(title='正文', file_name='content.xhtml')
        chapter.content = self._generate_html_content(data)
        book.add_item(chapter)
        
        # 添加导航
        book.toc = (epub.Link('content.xhtml', '正文', 'content'),)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 添加 CSS
        style = epub.EpubItem(uid="style", file_name="style.css", 
                             media_type="text/css", content=self._get_css())
        book.add_item(style)
        
        # 定义 spine
        book.spine = ['nav', chapter]
        
        # 写入文件
        epub.write_epub(output_path, book)
        return output_path
    
    def extract_text(self, file_path: str) -> str:
        """从 EPUB 提取纯文本"""
        from ebooklib import epub
        book = epub.read_epub(file_path)
        texts = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                texts.append(soup.get_text())
        return '\n'.join(texts)
```

### 4.2 EPUB 阅读器（前端）
```javascript
// doc-viewers/epub-viewer.js
class EPUBViewer extends Component {
    constructor(container) {
        super(container);
        this.book = null;
        this.rendition = null;
    }
    
    async load(url) {
        // 使用 epub.js
        this.book = ePub(url);
        this.rendition = this.book.renderTo(this.container, {
            width: '100%',
            height: '100%',
            flow: 'paginated'
        });
        
        this.rendition.display();
        
        // 绑定翻页事件
        this.bindNavigation();
    }
    
    bindNavigation() {
        // 键盘翻页
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.prevPage();
            if (e.key === 'ArrowRight') this.nextPage();
        });
    }
    
    nextPage() {
        this.rendition.next();
    }
    
    prevPage() {
        this.rendition.prev();
    }
    
    goToPage(pageNum) {
        // EPUB 使用 CFI 定位，需要转换
        this.rendition.display(this.book.locations.cfiFromPage(pageNum));
    }
    
    // 获取当前位置信息（用于语音播报同步）
    getCurrentLocation() {
        return this.rendition.currentLocation();
    }
}
```

### 4.3 EPUB 语音同步（高级功能）
```javascript
// 语音与 EPUB 阅读位置同步
class EPUBTTSController {
    constructor(epubViewer, ttsPlayer) {
        this.epubViewer = epubViewer;
        this.ttsPlayer = ttsPlayer;
        this.currentCFI = null;
    }
    
    // 根据语音进度同步 EPUB 位置
    syncWithAudio(currentTime, duration) {
        const progress = currentTime / duration;
        const cfi = this.epubViewer.book.locations.cfiFromPercentage(progress);
        this.epubViewer.rendition.display(cfi);
    }
    
    // 点击 EPUB 位置，从该位置开始播报
    startTTSFromCurrentLocation() {
        const location = this.epubViewer.getCurrentLocation();
        const text = this.extractTextFromLocation(location);
        this.ttsPlayer.play(text);
    }
}
```

---

## 5. 前端页面设计

### 5.1 页面布局
```
┌────────────────────────────────────────────────────────────────┐
│  报表中心                                           [🔔 刷新]  │
├──────────────┬─────────────────────────────────────────────────┤
│              │  📈 涨停报告 ▼                           [➕ 生成]│
│  📈 涨停报告  │  ┌─────────────────────────────────────────────┐│
│    (128)     │  │ 🔍 搜索...  📅 日期  📄 格式 ▼  🔊 仅语音就绪 ││
│              │  └─────────────────────────────────────────────┘│
│  📰 领域事件  │                                                 │
│    (45)      │  ┌─────────────────────────────────────────────┐│
│              │  │ 📚 涨停报告_20260402.epub           🔊 就绪  ││
│  📊 数据报表  │  │    📅 2026-04-02    📚 EPUB    2.0MB        ││
│    (32)      │  │    [👁️ 查看]  [🔊 播报 03:00]               ││
│              │  ├─────────────────────────────────────────────┤│
│  ➕ 其他      │  │ 📄 涨停报告_20260402.pdf            🔊 就绪  ││
│              │  │    📅 2026-04-02    📄 PDF     1.0MB        ││
│              │  │    [👁️ 查看]  [🔊 播报 03:00]               ││
│              │  ├─────────────────────────────────────────────┤│
│              │  │ 📝 涨停报告_20260402.md                    ││
│              │  │    📅 2026-04-02    📝 Markdown  50KB       ││
│              │  │    [👁️ 查看]  [⏳ 生成语音中...]            ││
│              │  └─────────────────────────────────────────────┘│
│              │              [上一页] 1/7 [下一页]               │
└──────────────┴─────────────────────────────────────────────────┘
```

### 5.2 EPUB 阅读器弹窗
```
┌────────────────────────────────────────────────────────────────┐
│  📚 涨停报告_20260402.epub              [×] [🔊 从当前页播报] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                                                         │  │
│  │              EPUB 内容渲染区域（epub.js）               │  │
│  │                                                         │  │
│  │    ┌─────────────────────────────────────────┐         │  │
│  │    │ 第一章 涨停概览                         │         │  │
│  │    │                                         │         │  │
│  │    │ 今日共有 45 只股票涨停...               │         │  │
│  │    │                                         │         │  │
│  │    │ [图表：涨停行业分布]                    │         │  │
│  │    │                                         │         │  │
│  │    │ 从行业分布来看，科技板块...             │         │  │
│  │    └─────────────────────────────────────────┘         │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  [←] 第 5 / 15 页 [→]    [📑 目录]    [🔖 书签]    [⚙️ 设置]  │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. 目录结构

### 6.1 文件存储
```
output/
├── zt_report/                    # 涨停报告
│   ├── 2026/
│   │   ├── 04/
│   │   │   ├── 涨停报告_20260402.pdf
│   │   │   ├── 涨停报告_20260402.epub
│   │   │   ├── 涨停报告_20260402.md
│   │   │   └── 涨停报告_20260402.html
│   │   └── 03/
├── event_report/                 # 领域事件报告
├── data_report/                  # 数据报表
└── tts_cache/                    # 语音缓存
    └── zt_report/
        └── 2026/
            └── 04/
                └── 涨停报告_20260402.mp3
```

### 6.2 前端第三方库
```
static/lib/
├── pdfjs/                   # PDF.js
├── mammoth/                 # Word 解析
├── sheetjs/                 # Excel 解析
├── marked/                  # Markdown 解析
└── epubjs/                  # EPUB.js（新增）
```

---

## 7. 开发计划

### Phase 1: 基础框架
- [ ] 数据库表创建（统一 report_ 前缀）
- [ ] ReportService 实现
- [ ] 基础 API 接口

### Phase 2: 文档预览
- [ ] PDF 预览（pdf.js）
- [ ] Word 预览（mammoth.js）
- [ ] Excel 预览（SheetJS）
- [ ] Markdown 预览（marked.js）
- [ ] **EPUB 预览（epub.js）**

### Phase 3: 语音播报
- [ ] Edge TTS 集成
- [ ] 语音生成 API
- [ ] 前端播放器组件

### Phase 4: 报告生成
- [ ] PDF/Word/Excel/Markdown/EPUB 导出器
- [ ] 涨停报告生成器
- [ ] 领域事件报告生成器

### Phase 5: 优化完善
- [ ] EPUB 语音同步（高级）
- [ ] 全文搜索
- [ ] 缓存优化

---

## 8. 技术选型

| 组件 | 选型 | 用途 |
|------|------|------|
| PDF | pdf.js | PDF 预览 |
| Word | mammoth.js | Word 转 HTML |
| Excel | SheetJS | Excel 解析 |
| Markdown | marked.js | Markdown 渲染 |
| **EPUB** | **epub.js** | **EPUB 阅读** |
| TTS | Edge TTS | 语音合成 |
| EPUB 生成 | ebooklib | Python EPUB 生成 |

---

## 9. 待确认问题

1. **EPUB 语音同步**：是否需要语音进度与 EPUB 阅读位置同步？
2. **EPUB 样式**：是否需要自定义 EPUB 主题样式？
3. **语音音色**：是否需要支持多种音色选择？
4. **Excel 播报**：表格数据如何播报？（仅摘要/关键数据？）
5. **语音缓存**：永久缓存还是定期清理？

请评审 V3 方案，确认后进入开发。
