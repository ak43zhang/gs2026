# 报表中心设计方案 V4（最终版）

## 1. 数据库架构

### 1.1 数据库配置
- **数据库名**: `gs_platform`
- **用途**: 存储所有平台级数据（报表中心、用户、配置等）
- **字符集**: `utf8mb4`
- **排序规则**: `utf8mb4_unicode_ci`

### 1.2 表清单
| 表名 | 说明 | 所属模块 |
|------|------|----------|
| `report_types` | 报告类型配置 | 报表中心 |
| `reports` | 报告元数据 | 报表中心 |
| `report_tasks` | 报告生成任务 | 报表中心 |

---

## 2. 数据库设计（gs_platform）

### 2.1 报告类型配置表
```sql
-- 表名: report_types
-- 说明: 配置支持的报告类型，支持动态扩展
-- 所属数据库: gs_platform

CREATE TABLE IF NOT EXISTS report_types (
    report_type_id          INT PRIMARY KEY AUTO_INCREMENT COMMENT '类型ID',
    report_type_code        VARCHAR(50) UNIQUE NOT NULL COMMENT '类型代码: zt_report/event_report',
    report_type_name        VARCHAR(100) NOT NULL COMMENT '类型名称: 涨停报告',
    report_type_icon        VARCHAR(50) DEFAULT '📄' COMMENT '图标',
    report_type_description TEXT COMMENT '类型描述',
    report_type_output_dir  VARCHAR(200) NOT NULL COMMENT '输出目录: zt_report',
    report_type_default_format VARCHAR(20) DEFAULT 'pdf' COMMENT '默认格式: pdf/epub',
    report_type_supported_formats JSON COMMENT '支持的格式列表: ["pdf","epub","md"]',
    report_type_is_active   BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    report_type_sort_order  INT DEFAULT 0 COMMENT '排序顺序',
    report_type_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_type_updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_report_type_active (report_type_is_active, report_type_sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告类型配置表';

-- 初始化数据
INSERT INTO report_types (
    report_type_code, report_type_name, report_type_icon, 
    report_type_output_dir, report_type_default_format, 
    report_type_supported_formats, report_type_sort_order
) VALUES
('zt_report', '涨停报告', '📈', 'zt_report', 'pdf', 
 '["pdf", "epub", "md", "html"]', 1),
('event_report', '领域事件报告', '📰', 'event_report', 'pdf', 
 '["pdf", "epub", "md", "docx"]', 2),
('data_report', '数据报表', '📊', 'data_report', 'xlsx', 
 '["xlsx", "pdf", "epub", "html"]', 3)
ON DUPLICATE KEY UPDATE 
    report_type_name = VALUES(report_type_name),
    report_type_supported_formats = VALUES(report_type_supported_formats);
```

### 2.2 报告元数据表
```sql
-- 表名: reports
-- 说明: 存储生成的报告元数据
-- 所属数据库: gs_platform

CREATE TABLE IF NOT EXISTS reports (
    report_id               INT PRIMARY KEY AUTO_INCREMENT COMMENT '报告ID',
    report_type             VARCHAR(50) NOT NULL COMMENT '报告类型代码',
    report_name             VARCHAR(255) NOT NULL COMMENT '报告名称: 涨停报告_20260402',
    report_date             DATE NOT NULL COMMENT '报告日期',
    report_file_path        VARCHAR(500) NOT NULL COMMENT '文件相对路径: zt_report/2026/04/xxx.pdf',
    report_file_format      VARCHAR(20) NOT NULL COMMENT '文件格式: pdf/epub/xlsx/md/html/txt',
    report_file_size        BIGINT DEFAULT 0 COMMENT '文件大小(字节)',
    report_page_count       INT DEFAULT 0 COMMENT '页数/章节数',
    report_content_text     LONGTEXT COMMENT '纯文本内容(用于搜索和TTS)',
    report_tts_status       VARCHAR(20) DEFAULT 'pending' COMMENT '语音状态: pending/running/completed/failed',
    report_tts_duration     INT DEFAULT 0 COMMENT '语音时长(秒)',
    report_tts_audio_path   VARCHAR(500) COMMENT '语音文件相对路径: tts_cache/...',
    report_params           JSON COMMENT '生成参数',
    report_status           VARCHAR(20) DEFAULT 'completed' COMMENT '报告状态: generating/completed/failed',
    report_created_at       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_report_type_date (report_type, report_date),
    INDEX idx_report_format (report_file_format),
    INDEX idx_report_date (report_date),
    INDEX idx_report_tts_status (report_tts_status),
    INDEX idx_report_status (report_status),
    FULLTEXT INDEX idx_report_content (report_content_text),
    
    -- 外键
    CONSTRAINT fk_report_type 
        FOREIGN KEY (report_type) REFERENCES report_types(report_type_code)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告元数据表';
```

### 2.3 报告生成任务表
```sql
-- 表名: report_tasks
-- 说明: 异步报告生成任务队列
-- 所属数据库: gs_platform

CREATE TABLE IF NOT EXISTS report_tasks (
    report_task_id          VARCHAR(50) PRIMARY KEY COMMENT '任务ID: zt_20260403_abc123',
    report_type             VARCHAR(50) NOT NULL COMMENT '报告类型',
    report_date             DATE NOT NULL COMMENT '报告日期',
    report_format           VARCHAR(20) COMMENT '目标格式',
    report_task_status      VARCHAR(20) DEFAULT 'pending' COMMENT '任务状态: pending/running/completed/failed',
    report_task_progress    INT DEFAULT 0 COMMENT '进度百分比 0-100',
    report_task_message     TEXT COMMENT '状态消息',
    report_task_params      JSON COMMENT '生成参数',
    report_task_result_id   INT COMMENT '生成的报告ID(关联reports表)',
    report_task_error       TEXT COMMENT '错误信息',
    report_task_started_at  DATETIME COMMENT '开始时间',
    report_task_completed_at DATETIME COMMENT '完成时间',
    report_task_created_at  DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    report_task_updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引
    INDEX idx_report_task_status (report_task_status),
    INDEX idx_report_task_type_date (report_type, report_date),
    INDEX idx_report_task_created (report_task_created_at),
    
    -- 外键
    CONSTRAINT fk_report_task_type 
        FOREIGN KEY (report_type) REFERENCES report_types(report_type_code)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_report_task_result 
        FOREIGN KEY (report_task_result_id) REFERENCES reports(report_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
COMMENT='报告生成任务表';
```

---

## 3. 项目目录结构

### 3.1 后端目录
```
src/gs2026/
├── dashboard2/
│   ├── routes/
│   │   ├── collection.py          # 数据采集路由
│   │   ├── analysis.py            # AI分析路由
│   │   └── report.py              # 【新增】报表中心路由
│   ├── services/
│   │   ├── report_service.py      # 【新增】报告服务
│   │   ├── report_generator.py    # 【新增】报告生成器
│   │   └── tts_service.py         # 【新增】语音播报服务
│   ├── models/
│   │   └── report_model.py        # 【新增】报告数据模型
│   └── config.py                  # 数据库配置（gs_platform）
├── report/                        # 【新增】报告生成模块
│   ├── __init__.py
│   ├── base.py                    # 报告基类
│   ├── zt_report/                # 涨停报告
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── event_report/             # 领域事件报告
│   │   ├── __init__.py
│   │   └── generator.py
│   └── exporters/                # 格式导出器
│       ├── __init__.py
│       ├── pdf_exporter.py
│       ├── epub_exporter.py      # 【新增】EPUB导出
│       ├── docx_exporter.py
│       ├── xlsx_exporter.py
│       └── md_exporter.py
└── output/                       # 报告输出目录
    ├── zt_report/               # 涨停报告
    ├── event_report/            # 领域事件报告
    ├── data_report/             # 数据报表
    └── tts_cache/               # 语音缓存
        ├── zt_report/
        ├── event_report/
        └── ...
```

### 3.2 前端目录
```
src/gs2026/dashboard2/static/
├── js/
│   ├── pages/
│   │   ├── collection-page.js
│   │   ├── analysis-page.js
│   │   └── report-page.js       # 【新增】报表中心页面
│   ├── modules/
│   │   ├── report-manager.js    # 【新增】报告管理器
│   │   ├── report-viewer.js     # 【新增】文档阅读器
│   │   └── tts-player.js        # 【新增】语音播放器
│   └── components/
│       ├── report-list.js       # 【新增】报告列表组件
│       └── doc-viewers/         # 【新增】文档阅读器集合
│           ├── pdf-viewer.js
│           ├── epub-viewer.js   # 【新增】EPUB阅读器
│           ├── docx-viewer.js
│           ├── xlsx-viewer.js
│           └── md-viewer.js
├── css/
│   └── report.css               # 【新增】报表样式
└── lib/                         # 【新增】第三方库
    ├── pdfjs/
    ├── epubjs/                  # 【新增】EPUB.js
    ├── mammoth/
    ├── sheetjs/
    └── marked/
```

---

## 4. API 接口设计

### 4.1 报告类型管理
```python
# GET /api/reports/types
# 获取报告类型列表
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
```

### 4.2 报告列表
```python
# GET /api/reports/list
# 参数: type, format, page, pageSize, startDate, endDate, keyword
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
                "report_file_path": "zt_report/2026/04/涨停报告_20260402.epub",
                "report_file_format": "epub",
                "report_file_size": 2048576,
                "report_page_count": 15,
                "report_tts_status": "completed",
                "report_tts_duration": 180,
                "report_created_at": "2026-04-02 18:30:00"
            }
        ]
    }
}
```

### 4.3 报告详情与预览
```python
# GET /api/reports/{report_id}
{
    "success": true,
    "data": {
        "report_id": 1,
        "report_name": "涨停报告_20260402",
        "report_file_format": "epub",
        "report_view_url": "/api/reports/file/1/view",
        "report_content_text": "...纯文本内容...",
        "report_tts_status": "completed",
        "report_tts_audio_url": "/api/reports/1/tts/audio",
        "report_tts_duration": 180
    }
}

# GET /api/reports/file/{report_id}/view
# 根据格式返回不同内容
# - PDF: 文件流
# - EPUB: 文件流
# - Word: 转换后的HTML
# - Excel: JSON数据
# - Markdown: 渲染后的HTML
```

### 4.4 语音播报
```python
# POST /api/reports/{report_id}/tts/generate
# 请求体: {"voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0}
{
    "success": true,
    "data": {
        "report_task_id": "tts_123456",
        "report_task_status": "running"
    }
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
# 返回: MP3音频流
```

### 4.5 报告生成
```python
# POST /api/reports/generate
# 请求体: {"type": "zt_report", "date": "2026-04-03", "format": "epub"}
{
    "success": true,
    "data": {
        "report_task_id": "zt_20260403_abc123",
        "report_task_status": "pending"
    }
}

# GET /api/reports/tasks/{task_id}/status
{
    "success": true,
    "data": {
        "report_task_id": "zt_20260403_abc123",
        "report_task_status": "running",
        "report_task_progress": 65,
        "report_task_message": "正在生成图表..."
    }
}
```

### 4.6 报告删除
```python
# DELETE /api/reports/{report_id}
# 删除报告（同时删除文件和语音）
{
    "success": true,
    "message": "报告已删除"
}
```

---

## 5. 核心组件设计

### 5.1 数据库模型（gs_platform）
```python
# models/report_model.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean, BigInt, JSON, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class ReportType(Base):
    """报告类型配置"""
    __tablename__ = 'report_types'
    __table_args__ = {'schema': 'gs_platform'}
    
    report_type_id = Column(Integer, primary_key=True, autoincrement=True)
    report_type_code = Column(String(50), unique=True, nullable=False)
    report_type_name = Column(String(100), nullable=False)
    report_type_icon = Column(String(50), default='📄')
    report_type_description = Column(Text)
    report_type_output_dir = Column(String(200), nullable=False)
    report_type_default_format = Column(String(20), default='pdf')
    report_type_supported_formats = Column(JSON)
    report_type_is_active = Column(Boolean, default=True)
    report_type_sort_order = Column(Integer, default=0)
    report_type_created_at = Column(DateTime, default=datetime.now)
    report_type_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Report(Base):
    """报告元数据"""
    __tablename__ = 'reports'
    __table_args__ = (
        Index('idx_report_type_date', 'report_type', 'report_date'),
        Index('idx_report_format', 'report_file_format'),
        {'schema': 'gs_platform'}
    )
    
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(50), ForeignKey('gs_platform.report_types.report_type_code'), nullable=False)
    report_name = Column(String(255), nullable=False)
    report_date = Column(Date, nullable=False)
    report_file_path = Column(String(500), nullable=False)
    report_file_format = Column(String(20), nullable=False)
    report_file_size = Column(BigInt, default=0)
    report_page_count = Column(Integer, default=0)
    report_content_text = Column(Text)
    report_tts_status = Column(String(20), default='pending')
    report_tts_duration = Column(Integer, default=0)
    report_tts_audio_path = Column(String(500))
    report_params = Column(JSON)
    report_status = Column(String(20), default='completed')
    report_created_at = Column(DateTime, default=datetime.now)
    report_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    report_type_ref = relationship("ReportType", backref="reports")

class ReportTask(Base):
    """报告生成任务"""
    __tablename__ = 'report_tasks'
    __table_args__ = {'schema': 'gs_platform'}
    
    report_task_id = Column(String(50), primary_key=True)
    report_type = Column(String(50), ForeignKey('gs_platform.report_types.report_type_code'), nullable=False)
    report_date = Column(Date, nullable=False)
    report_format = Column(String(20))
    report_task_status = Column(String(20), default='pending')
    report_task_progress = Column(Integer, default=0)
    report_task_message = Column(Text)
    report_task_params = Column(JSON)
    report_task_result_id = Column(Integer, ForeignKey('gs_platform.reports.report_id'))
    report_task_error = Column(Text)
    report_task_started_at = Column(DateTime)
    report_task_completed_at = Column(DateTime)
    report_task_created_at = Column(DateTime, default=datetime.now)
    report_task_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    report_result = relationship("Report", backref="generation_task")
```

### 5.2 报告服务
```python
# services/report_service.py
class ReportService:
    """报告服务 - 管理报告元数据和文件"""
    
    def __init__(self, db_session, output_root: Path):
        self.db = db_session
        self.output_root = output_root
    
    def list_reports(self, filters: dict) -> dict:
        """获取报告列表（按时间倒序）"""
        pass
    
    def get_report(self, report_id: int) -> Report:
        """获取报告详情"""
        pass
    
    def create_report(self, data: dict) -> Report:
        """创建报告记录"""
        pass
    
    def delete_report(self, report_id: int) -> bool:
        """删除报告（同时删除文件和语音）"""
        pass
    
    def get_file_path(self, report: Report) -> Path:
        """获取文件绝对路径"""
        return self.output_root / report.report_file_path
```

### 5.3 报告生成器
```python
# report/base.py
from abc import ABC, abstractmethod

class ReportGenerator(ABC):
    """报告生成器基类"""
    
    @abstractmethod
    def generate(self, report_date: date, format: str, params: dict) -> dict:
        """
        生成报告
        返回: {
            'file_path': '相对路径',
            'file_size': 1024,
            'page_count': 10,
            'content_text': '纯文本内容'
        }
        """
        pass
    
    @abstractmethod
    def get_report_name(self, report_date: date) -> str:
        """生成报告文件名"""
        pass
```

### 5.4 语音播报服务
```python
# services/tts_service.py
import edge_tts
import asyncio

class TTSService:
    """语音播报服务 - 使用 Edge TTS"""
    
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.voices = {
            'xiaoxiao': 'zh-CN-XiaoxiaoNeural',
            'xiaoyi': 'zh-CN-XiaoyiNeural',
            'yunjian': 'zh-CN-YunjianNeural',
            'yunxi': 'zh-CN-YunxiNeural'
        }
    
    async def generate(self, text: str, output_path: Path, 
                       voice: str = 'xiaoxiao', speed: float = 1.0) -> dict:
        """生成语音文件"""
        voice_id = self.voices.get(voice, self.voices['xiaoxiao'])
        communicate = edge_tts.Communicate(text, voice_id, rate=f"{int((speed-1)*100)}%")
        await communicate.save(str(output_path))
        
        # 获取音频时长
        duration = self._get_audio_duration(output_path)
        return {
            'audio_path': str(output_path),
            'duration': duration,
            'file_size': output_path.stat().st_size
        }
    
    def generate_for_report(self, report: Report) -> str:
        """为报告生成语音"""
        # 1. 提取/分段文本
        # 2. 异步生成音频
        # 3. 合并音频（如需要）
        # 4. 保存到缓存目录
        pass
```

---

## 6. 开发任务清单

### Phase 1: 数据库与基础架构
- [ ] 创建 `gs_platform` 数据库
- [ ] 执行 SQL 建表脚本（3张表）
- [ ] 配置 SQLAlchemy 模型
- [ ] 数据库连接配置

### Phase 2: 后端 API
- [ ] `GET /api/reports/types` - 报告类型列表
- [ ] `GET /api/reports/list` - 报告列表
- [ ] `GET /api/reports/{id}` - 报告详情
- [ ] `GET /api/reports/file/{id}/view` - 文件预览
- [ ] `POST /api/reports/{id}/tts/generate` - 生成语音
- [ ] `GET /api/reports/{id}/tts/status` - 语音状态
- [ ] `GET /api/reports/{id}/tts/audio` - 获取语音
- [ ] `POST /api/reports/generate` - 生成报告
- [ ] `GET /api/reports/tasks/{id}/status` - 任务状态
- [ ] `DELETE /api/reports/{id}` - 删除报告

### Phase 3: 前端页面
- [ ] 报表中心页面框架
- [ ] 左侧类型导航组件
- [ ] 报告列表组件
- [ ] 文档阅读器容器
- [ ] 语音播放器组件

### Phase 4: 文档预览
- [ ] PDF 阅读器（pdf.js）
- [ ] EPUB 阅读器（epub.js）
- [ ] Word 阅读器（mammoth.js）
- [ ] Excel 阅读器（SheetJS）
- [ ] Markdown 阅读器（marked.js）

### Phase 5: 报告生成
- [ ] PDF 导出器
- [ ] EPUB 导出器
- [ ] Word 导出器
- [ ] Excel 导出器
- [ ] Markdown 导出器
- [ ] 涨停报告生成器
- [ ] 领域事件报告生成器

### Phase 6: 语音播报
- [ ] Edge TTS 集成
- [ ] 语音生成任务队列
- [ ] 前端播放器
- [ ] 播放控制条

---

## 7. 配置文件

### 7.1 数据库配置
```python
# config.py
DATABASES = {
    'gs': {
        'host': '192.168.0.101',
        'port': 3306,
        'database': 'gs',
        'user': 'root',
        'password': '123456'
    },
    'gs_platform': {  # 【新增】平台数据库
        'host': '192.168.0.101',
        'port': 3306,
        'database': 'gs_platform',
        'user': 'root',
        'password': '123456'
    }
}
```

### 7.2 报告输出配置
```python
# config.py
REPORT_CONFIG = {
    'output_root': 'F:/pyworkspace2026/gs2026/output',
    'supported_formats': ['pdf', 'epub', 'docx', 'xlsx', 'md', 'html', 'txt'],
    'tts_cache_dir': 'tts_cache',
    'max_file_size': 50 * 1024 * 1024,  # 50MB
    'page_size': 20
}
```

---

## 8. 部署检查清单

- [ ] 确认 MySQL 已创建 `gs_platform` 数据库
- [ ] 执行建表 SQL 脚本
- [ ] 安装依赖：`pip install edge-tts ebooklib python-docx openpyxl`
- [ ] 创建输出目录：`output/{zt_report,event_report,data_report,tts_cache}`
- [ ] 配置数据库连接
- [ ] 测试 API 接口
- [ ] 部署前端第三方库（pdf.js, epub.js 等）

---

## 9. 技术栈总结

| 层级 | 技术 | 用途 |
|------|------|------|
| 数据库 | MySQL + SQLAlchemy | gs_platform 数据存储 |
| 后端 | Flask + Python | API 服务 |
| 前端 | Vanilla JS + Component | 页面交互 |
| PDF | pdf.js | PDF 预览 |
| EPUB | epub.js | EPUB 预览 |
| Word | mammoth.js | Word 转 HTML |
| Excel | SheetJS | Excel 解析 |
| Markdown | marked.js | Markdown 渲染 |
| TTS | edge-tts | 语音合成 |
| EPUB生成 | ebooklib | Python EPUB 生成 |

---

## 10. 进入开发

方案已最终确认，开始开发阶段。
