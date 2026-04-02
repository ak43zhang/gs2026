# 报表中心设计方案 V2

## 1. 需求概述

### 1.1 功能目标
- 支持多种文档格式（PDF、Word、Excel、Markdown、HTML 等）
- 报告在指定目录保存，前端可查看和阅读
- 支持语音播报功能（TTS）
- 多种报告类型（涨停报告、领域事件报告等，可扩展）
- 所有报告按时间倒序排列
- 暂不支持下载功能

### 1.2 支持文档格式
| 格式 | 扩展名 | 预览方式 | 语音播报 |
|------|--------|----------|----------|
| PDF | .pdf | pdf.js / 浏览器原生 | ✅ 支持 |
| Word | .docx | mammoth.js 转 HTML | ✅ 支持 |
| Excel | .xlsx | SheetJS / 表格渲染 | ⚠️ 部分支持（摘要播报） |
| Markdown | .md | marked.js 渲染 | ✅ 支持 |
| HTML | .html | iframe 直接显示 | ✅ 支持 |
| 文本 | .txt | 纯文本显示 | ✅ 支持 |

### 1.3 报告类型
| 类型 | 说明 | 默认格式 |
|------|------|----------|
| 涨停报告 | 每日涨停股票分析报告 | PDF |
| 领域事件报告 | 行业/领域重大事件报告 | PDF/Markdown |
| 数据报表 | 统计数据表格 | Excel |
| 其他 | 预留扩展位 | 任意 |

---

## 2. 目录结构设计

### 2.1 后端目录
```
src/gs2026/
├── dashboard2/
│   ├── routes/
│   │   ├── collection.py
│   │   ├── analysis.py
│   │   └── report.py              # 新增：报表中心路由
│   ├── services/
│   │   ├── report_service.py      # 新增：报告服务
│   │   ├── report_generator.py    # 新增：报告生成器基类
│   │   └── tts_service.py         # 新增：语音播报服务
│   └── models/
│       └── report.py              # 新增：报告数据模型
├── report/                        # 新增：报告生成模块
│   ├── __init__.py
│   ├── base.py                    # 报告基类
│   ├── zt_report/                # 涨停报告
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── event_report/             # 领域事件报告
│   │   ├── __init__.py
│   │   └── generator.py
│   └── exporters/                # 导出器（多种格式）
│       ├── __init__.py
│       ├── pdf_exporter.py
│       ├── docx_exporter.py
│       ├── xlsx_exporter.py
│       └── md_exporter.py
└── output/                       # 报告输出目录
    ├── zt_report/               # 涨停报告
    │   ├── 2026/04/
    │   │   ├── 涨停报告_20260402.pdf
    │   │   └── 涨停报告_20260402.md
    ├── event_report/            # 领域事件报告
    └── data_report/             # 数据报表
```

### 2.2 前端目录
```
src/gs2026/dashboard2/static/
├── js/
│   ├── pages/
│   │   └── report-page.js       # 新增：报表中心页面
│   ├── modules/
│   │   ├── report-manager.js    # 新增：报告管理器
│   │   ├── report-viewer.js     # 新增：文档阅读器组件
│   │   └── tts-player.js        # 新增：语音播报组件
│   └── components/
│       ├── report-list.js       # 新增：报告列表组件
│       └── doc-viewers/         # 新增：多种文档阅读器
│           ├── pdf-viewer.js
│           ├── docx-viewer.js
│           ├── xlsx-viewer.js
│           └── md-viewer.js
├── css/
│   └── report.css               # 新增：报表样式
└── lib/                         # 新增：第三方库
    ├── pdfjs/                   # PDF.js
    ├── mammoth/                 # Word 解析
    ├── sheetjs/                 # Excel 解析
    └── marked/                  # Markdown 解析
```

---

## 3. 数据库设计

### 3.1 报告元数据表
```sql
CREATE TABLE reports (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    report_type     VARCHAR(50) NOT NULL,          -- 报告类型
    report_name     VARCHAR(255) NOT NULL,         -- 报告名称
    report_date     DATE NOT NULL,                 -- 报告日期
    file_path       VARCHAR(500) NOT NULL,         -- 文件路径
    file_format     VARCHAR(20) NOT NULL,          -- 文件格式: pdf, docx, xlsx, md, html, txt
    file_size       BIGINT,                        -- 文件大小(字节)
    page_count      INT,                           -- 页数/段落数（可选）
    content_text    LONGTEXT,                      -- 纯文本内容（用于搜索和语音播报）
    tts_status      VARCHAR(20) DEFAULT 'pending', -- 语音状态: pending, ready, failed
    tts_duration    INT,                           -- 语音时长(秒)
    params          JSON,                          -- 生成参数
    status          VARCHAR(20) DEFAULT 'completed',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_type_date (report_type, report_date),
    INDEX idx_format (file_format),
    INDEX idx_date (report_date),
    FULLTEXT INDEX idx_content (content_text)      -- 全文搜索
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.2 报告类型配置表
```sql
CREATE TABLE report_types (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    type_code       VARCHAR(50) UNIQUE NOT NULL,
    type_name       VARCHAR(100) NOT NULL,
    icon            VARCHAR(50),
    description     TEXT,
    output_dir      VARCHAR(200) NOT NULL,
    default_format  VARCHAR(20) DEFAULT 'pdf',     -- 默认生成格式
    supported_formats JSON,                        -- 支持的格式列表
    is_active       BOOLEAN DEFAULT TRUE,
    sort_order      INT DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始化数据
INSERT INTO report_types (type_code, type_name, icon, output_dir, default_format, supported_formats) VALUES
('zt_report', '涨停报告', '📈', 'zt_report', 'pdf', '["pdf", "md", "html"]'),
('event_report', '领域事件报告', '📰', 'event_report', 'pdf', '["pdf", "md", "docx"]'),
('data_report', '数据报表', '📊', 'data_report', 'xlsx', '["xlsx", "pdf", "html"]');
```

### 3.3 语音播报缓存表
```sql
CREATE TABLE tts_cache (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    report_id       INT NOT NULL,
    audio_path      VARCHAR(500) NOT NULL,         -- 音频文件路径
    audio_format    VARCHAR(10) DEFAULT 'mp3',     -- 音频格式
    duration        INT,                           -- 时长(秒)
    file_size       BIGINT,                        -- 文件大小
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY uk_report (report_id),
    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 4. API 设计

### 4.1 报告管理接口
```python
# GET /api/reports/types
# 获取报告类型列表
{
    "success": true,
    "data": [
        {
            "code": "zt_report",
            "name": "涨停报告",
            "icon": "📈",
            "count": 128,
            "default_format": "pdf",
            "supported_formats": ["pdf", "md", "html"]
        }
    ]
}

# GET /api/reports/list?type=zt_report&format=pdf&page=1&pageSize=20
# 获取报告列表（按时间倒序）
{
    "success": true,
    "data": {
        "total": 128,
        "page": 1,
        "pageSize": 20,
        "list": [
            {
                "id": 1,
                "report_type": "zt_report",
                "report_name": "涨停报告_20260402",
                "report_date": "2026-04-02",
                "file_path": "/output/zt_report/2026/04/涨停报告_20260402.pdf",
                "file_format": "pdf",
                "file_size": 1024576,
                "page_count": 15,
                "tts_status": "ready",           # 语音状态
                "tts_duration": 180,              # 语音时长3分钟
                "created_at": "2026-04-02 18:30:00"
            }
        ]
    }
}

# GET /api/reports/{id}
# 获取报告详情
{
    "success": true,
    "data": {
        "id": 1,
        "report_name": "涨停报告_20260402",
        "file_format": "pdf",
        "view_url": "/api/reports/file/1/view",
        "content_text": "...报告纯文本内容...",
        "tts_audio_url": "/api/reports/1/tts/audio"  # 语音文件URL
    }
}

# GET /api/reports/file/{id}/view
# 文档预览（根据格式返回不同内容）
# - PDF: 直接返回文件流
# - Word: 转换为 HTML 后返回
# - Excel: 返回 JSON 数据
# - Markdown: 返回渲染后的 HTML

# POST /api/reports/{id}/tts/generate
# 生成语音播报
{
    "voice": "zh-CN-XiaoxiaoNeural",  # 可选：指定音色
    "speed": 1.0                       # 可选：语速
}
# 返回: {"success": true, "task_id": "tts_123", "status": "running"}

# GET /api/reports/{id}/tts/status
# 查询语音生成状态
{
    "success": true,
    "data": {
        "status": "completed",  # pending, running, completed, failed
        "progress": 100,
        "audio_url": "/api/reports/1/tts/audio",
        "duration": 180
    }
}

# GET /api/reports/{id}/tts/audio
# 获取语音文件（MP3 流）

# POST /api/reports/generate
# 手动触发报告生成
{
    "type": "zt_report",
    "date": "2026-04-03",
    "format": "pdf",           # 可选，默认使用类型配置
    "params": {}
}

# DELETE /api/reports/{id}
# 删除报告（同时删除关联文件和语音）
```

---

## 5. 前端页面设计

### 5.1 页面布局
```
┌─────────────────────────────────────────────────────────────┐
│  报表中心                                        [🔔 刷新]  │
├──────────────┬──────────────────────────────────────────────┤
│              │  📈 涨停报告 ▼                      [➕ 生成] │
│  📈 涨停报告  │  ┌─────────────────────────────────────────┐ │
│    (128)     │  │ 🔍 搜索...    📅 日期      📄 格式 ▼   │ │
│              │  └─────────────────────────────────────────┘ │
│  📰 领域事件  │                                            │
│    (45)      │  ┌─────────────────────────────────────────┐ │
│              │  │ 📄 涨停报告_20260402.pdf          🔊   │ │
│  📊 数据报表  │  │    📅 2026-04-02    ⏱️ 15页    1.0MB  │ │
│    (32)      │  │    [👁️ 查看]  [🔊 播报 03:00]         │ │
│              │  ├─────────────────────────────────────────┤ │
│  ➕ 其他      │  │ 📝 涨停报告_20260402.md           🔊   │ │
│              │  │    📅 2026-04-02    📝 Markdown  50KB  │ │
│              │  │    [👁️ 查看]  [🔊 播报 02:30]         │ │
│              │  ├─────────────────────────────────────────┤ │
│              │  │ 📊 涨停数据_20260402.xlsx                │ │
│              │  │    📅 2026-04-02    📊 Excel     120KB │ │
│              │  │    [👁️ 查看]  [🔊 播报 01:00]         │ │
│              │  └─────────────────────────────────────────┘ │
│              │           [上一页] 1/7 [下一页]              │
└──────────────┴──────────────────────────────────────────────┘
```

### 5.2 文档阅读器弹窗
```
┌─────────────────────────────────────────────────────────────┐
│  涨停报告_20260402.pdf                    [×] [🔊 播报]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │              文档内容预览区域                        │   │
│  │                                                     │   │
│  │         • PDF: pdf.js 渲染                          │   │
│  │         • Word: HTML 渲染                           │   │
│  │         • Excel: 表格渲染                           │   │
│  │         • Markdown: 富文本渲染                      │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [←] 第 5 / 15 页 [→]      [+] 放大 [-] 缩小              │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 语音播报控制条
```
┌─────────────────────────────────────────────────────────────┐
│  🔊 正在播报: 涨停报告_20260402.pdf    [⏸️ 暂停] [⏹️ 停止] │
│  00:45 / 03:00  [==============================>      ]  │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 核心组件设计

### 6.1 文档阅读器工厂
```javascript
// doc-viewer-factory.js
class DocViewerFactory {
    static createViewer(format) {
        switch(format) {
            case 'pdf': return new PDFViewer();
            case 'docx': return new DocxViewer();
            case 'xlsx': return new XlsxViewer();
            case 'md': return new MarkdownViewer();
            case 'txt': return new TextViewer();
            default: return new DefaultViewer();
        }
    }
}
```

### 6.2 语音播报服务
```python
# tts_service.py
class TTSService:
    """语音播报服务"""
    
    def __init__(self):
        self.engine = self._init_tts_engine()
    
    def generate(self, text: str, voice: str = "zh-CN-XiaoxiaoNeural", 
                 speed: float = 1.0) -> str:
        """生成语音文件，返回音频路径"""
        pass
    
    def generate_for_report(self, report_id: int) -> str:
        """为报告生成语音"""
        # 1. 获取报告纯文本内容
        # 2. 分段生成语音（避免过长）
        # 3. 合并音频文件
        # 4. 保存到 tts_cache 表
        pass
    
    def get_audio_path(self, report_id: int) -> str:
        """获取语音文件路径（优先从缓存）"""
        pass
```

### 6.3 报告导出器基类
```python
# exporters/base.py
class ReportExporter(ABC):
    """报告导出器基类"""
    
    @property
    @abstractmethod
    def format(self) -> str:
        pass
    
    @abstractmethod
    def export(self, data: dict, output_path: str) -> str:
        """导出报告，返回文件路径"""
        pass
    
    def extract_text(self, file_path: str) -> str:
        """提取纯文本内容（用于语音播报）"""
        pass

# exporters/pdf_exporter.py
class PDFExporter(ReportExporter):
    format = 'pdf'
    
    def export(self, data: dict, output_path: str) -> str:
        # 使用 reportlab 生成 PDF
        pass
    
    def extract_text(self, file_path: str) -> str:
        # 使用 PyPDF2 提取文本
        pass

# exporters/docx_exporter.py
class DocxExporter(ReportExporter):
    format = 'docx'
    
    def export(self, data: dict, output_path: str) -> str:
        # 使用 python-docx 生成 Word
        pass
```

### 6.4 前端 TTS 播放器
```javascript
// tts-player.js
class TTSPlayer extends Component {
    constructor() {
        this.audio = new Audio();
        this.isPlaying = false;
        this.currentReport = null;
    }
    
    async load(reportId) {
        // 获取音频 URL
        const audioUrl = `/api/reports/${reportId}/tts/audio`;
        this.audio.src = audioUrl;
    }
    
    play() {
        this.audio.play();
        this.isPlaying = true;
    }
    
    pause() {
        this.audio.pause();
        this.isPlaying = false;
    }
    
    stop() {
        this.audio.pause();
        this.audio.currentTime = 0;
        this.isPlaying = false;
    }
    
    // 显示播放控制条
    showControlBar() {}
    hideControlBar() {}
}
```

---

## 7. 文件存储策略

### 7.1 目录结构
```
output/
├── zt_report/                    # 涨停报告
│   ├── 2026/
│   │   ├── 04/
│   │   │   ├── 涨停报告_20260402.pdf
│   │   │   ├── 涨停报告_20260402.md
│   │   │   └── 涨停报告_20260402.html
│   │   └── 03/
├── event_report/                 # 领域事件报告
├── data_report/                  # 数据报表
└── tts_cache/                    # 语音缓存
    ├── zt_report/
    │   └── 2026/
    │       └── 04/
    │           └── 涨停报告_20260402.mp3
    └── ...
```

### 7.2 命名规范
- 涨停报告：`涨停报告_YYYYMMDD.{format}`
- 领域事件报告：`领域事件报告_YYYYMMDD.{format}`
- 语音文件：`{report_name}.mp3`

---

## 8. 语音播报实现方案

### 8.1 TTS 引擎选择
| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Edge TTS** | 免费、中文效果好、无需 API Key | 需要联网 | ⭐⭐⭐⭐⭐ |
| Azure TTS | 专业、音色丰富 | 需要订阅 | ⭐⭐⭐⭐ |
| 讯飞/百度 | 国内稳定 | 需要付费 | ⭐⭐⭐ |
| 本地 TTS | 离线可用 | 效果一般 | ⭐⭐ |

### 8.2 推荐方案：Edge TTS
```python
# 使用 edge-tts 库
import edge_tts
import asyncio

async def generate_tts(text: str, output_file: str, voice: str = "zh-CN-XiaoxiaoNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
```

### 8.3 语音生成流程
```
1. 用户点击 [🔊 播报] 按钮
        ↓
2. 检查 tts_cache 表是否有缓存
        ↓
   ├─ 有缓存 → 直接返回音频 URL
   └─ 无缓存 → 开始生成
        ↓
3. 提取报告纯文本内容
        ↓
4. 分段处理（每段 < 5000 字符）
        ↓
5. 调用 Edge TTS 生成音频片段
        ↓
6. 合并音频片段（使用 pydub）
        ↓
7. 保存到 tts_cache 目录
        ↓
8. 更新 tts_cache 表记录
        ↓
9. 返回音频 URL
```

---

## 9. 扩展性设计

### 9.1 新增报告类型
1. 在 `report_types` 表添加记录
2. 创建 `report/{type}/generator.py`
3. 在 `ReportGeneratorFactory` 注册

### 9.2 新增文档格式
1. 创建 `exporters/{format}_exporter.py`
2. 创建 `doc-viewers/{format}-viewer.js`
3. 更新 `report_types.supported_formats`

### 9.3 新增 TTS 引擎
1. 实现 `TTSEngine` 接口
2. 在 `TTSService` 中注册

---

## 10. 开发计划

### Phase 1: 基础框架
- [ ] 数据库表创建
- [ ] ReportService 实现
- [ ] 基础 API 接口
- [ ] 前端页面框架

### Phase 2: 文档预览
- [ ] PDF 预览（pdf.js）
- [ ] Word 预览（mammoth.js）
- [ ] Excel 预览（SheetJS）
- [ ] Markdown 预览（marked.js）

### Phase 3: 语音播报
- [ ] Edge TTS 集成
- [ ] 语音生成 API
- [ ] 前端播放器组件
- [ ] 播放控制条

### Phase 4: 报告生成
- [ ] 报告生成器基类
- [ ] PDF/Word/Excel 导出器
- [ ] 涨停报告生成器
- [ ] 领域事件报告生成器

### Phase 5: 优化完善
- [ ] 全文搜索
- [ ] 批量操作
- [ ] 缓存优化
- [ ] 错误处理

---

## 11. 技术选型确认

| 组件 | 选型 | 说明 |
|------|------|------|
| PDF 预览 | **pdf.js** | Mozilla 开源，功能完善 |
| Word 预览 | **mammoth.js** | 轻量，转换效果好 |
| Excel 预览 | **SheetJS** | 功能强大，社区活跃 |
| Markdown | **marked.js** | 简洁高效 |
| TTS 引擎 | **Edge TTS** | 免费、中文效果好 |
| 音频处理 | **pydub** | Python 音频处理库 |

---

## 12. 待确认问题

1. **语音播报音色**：是否需要支持多种音色选择？
2. **Excel 播报**：表格数据如何播报？（仅播报摘要/关键数据？）
3. **语音缓存策略**：永久缓存还是定期清理？
4. **并发生成**：是否支持多个报告同时生成语音？
5. **移动端适配**：是否需要支持移动端语音播放？

请评审以上方案，确认后进入开发阶段。
