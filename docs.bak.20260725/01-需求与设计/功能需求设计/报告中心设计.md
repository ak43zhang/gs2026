# 报表中心设计方案

## 1. 需求概述

### 1.1 功能目标
- PDF 报告生成后在指定目录保存
- 前端可查看和阅读指定报告
- 支持多种报告类型（涨停报告、领域事件报告等）
- 按时间倒序排列报告列表

### 1.2 报告类型
| 类型 | 说明 | 扩展性 |
|------|------|--------|
| 涨停报告 | 每日涨停股票分析报告 | 基础类型 |
| 领域事件报告 | 行业/领域重大事件报告 | 基础类型 |
| 其他 | 预留扩展位 | 可动态添加 |

---

## 2. 目录结构设计

### 2.1 后端目录
```
src/gs2026/
├── dashboard2/
│   ├── routes/
│   │   ├── collection.py      # 现有：数据采集
│   │   ├── analysis.py        # 现有：AI分析
│   │   └── report.py          # 新增：报表中心
│   ├── services/
│   │   ├── report_service.py  # 新增：报告服务
│   │   └── report_generator.py # 新增：报告生成器
│   └── models/
│       └── report.py          # 新增：报告数据模型
├── report/                    # 新增：报告生成模块
│   ├── __init__.py
│   ├── zt_report/            # 涨停报告
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── event_report/         # 领域事件报告
│   │   ├── __init__.py
│   │   └── generator.py
│   └── base.py               # 报告基类
└── output/                   # 报告输出目录（已存在）
    ├── zt_report/           # 涨停报告输出
    ├── event_report/        # 领域事件报告输出
    └── ...                  # 其他报告类型
```

### 2.2 前端目录
```
src/gs2026/dashboard2/static/
├── js/
│   ├── pages/
│   │   ├── collection-page.js  # 现有
│   │   ├── analysis-page.js    # 现有
│   │   └── report-page.js      # 新增：报表中心页面
│   ├── modules/
│   │   ├── report-manager.js   # 新增：报告管理器
│   │   └── report-viewer.js    # 新增：PDF阅读器组件
│   └── components/
│       └── report-list.js      # 新增：报告列表组件
└── css/
    └── report.css              # 新增：报表样式
```

---

## 3. 数据库设计

### 3.1 报告元数据表
```sql
CREATE TABLE reports (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    report_type     VARCHAR(50) NOT NULL,      -- 报告类型: zt_report, event_report
    report_name     VARCHAR(255) NOT NULL,     -- 报告名称
    report_date     DATE NOT NULL,             -- 报告日期
    file_path       VARCHAR(500) NOT NULL,     -- 文件路径
    file_size       BIGINT,                    -- 文件大小(字节)
    page_count      INT,                       -- 页数
    params          JSON,                      -- 生成参数
    status          VARCHAR(20) DEFAULT 'completed', -- 状态: generating, completed, failed
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_type_date (report_type, report_date),
    INDEX idx_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.2 报告类型配置表（支持动态扩展）
```sql
CREATE TABLE report_types (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    type_code       VARCHAR(50) UNIQUE NOT NULL,  -- 类型代码
    type_name       VARCHAR(100) NOT NULL,        -- 类型名称
    icon            VARCHAR(50),                   -- 图标
    description     TEXT,                          -- 描述
    output_dir      VARCHAR(200) NOT NULL,        -- 输出目录
    is_active       BOOLEAN DEFAULT TRUE,         -- 是否启用
    sort_order      INT DEFAULT 0,                -- 排序
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 初始化数据
INSERT INTO report_types (type_code, type_name, icon, output_dir, sort_order) VALUES
('zt_report', '涨停报告', '📈', 'zt_report', 1),
('event_report', '领域事件报告', '📰', 'event_report', 2);
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
        {"code": "zt_report", "name": "涨停报告", "icon": "📈", "count": 128},
        {"code": "event_report", "name": "领域事件报告", "icon": "📰", "count": 45}
    ]
}

# GET /api/reports/list?type=zt_report&page=1&pageSize=20&startDate=2026-03-01&endDate=2026-04-03
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
                "file_path": "/output/zt_report/涨停报告_20260402.pdf",
                "file_size": 1024576,
                "page_count": 15,
                "created_at": "2026-04-02 18:30:00"
            }
        ]
    }
}

# GET /api/reports/view/{id}
# 获取报告查看信息
{
    "success": true,
    "data": {
        "id": 1,
        "report_name": "涨停报告_20260402",
        "view_url": "/api/reports/file/zt_report/涨停报告_20260402.pdf",
        "download_url": "/api/reports/download/1"
    }
}

# GET /api/reports/file/{type}/{filename}
# PDF 文件访问（支持浏览器预览）

# POST /api/reports/generate
# 手动触发报告生成
{
    "type": "zt_report",
    "date": "2026-04-03",
    "params": {}
}

# DELETE /api/reports/{id}
# 删除报告（仅删除记录，保留文件或可选删除）
```

### 4.2 报告生成任务接口
```python
# GET /api/reports/tasks
# 获取生成任务列表

# GET /api/reports/tasks/{id}/status
# 获取任务状态
{
    "success": true,
    "data": {
        "task_id": "zt_report_20260403_abc123",
        "status": "running",  # pending, running, completed, failed
        "progress": 65,
        "message": "正在生成图表..."
    }
}
```

---

## 5. 前端页面设计

### 5.1 页面布局
```
┌─────────────────────────────────────────────────────────┐
│  报表中心                                    [刷新]      │
├────────────┬────────────────────────────────────────────┤
│            │  涨停报告 ▼                    [生成新报告] │
│  📈 涨停报告 │  ┌─────────────────────────────────────┐  │
│    (128)   │  │ 🔍 搜索...    📅 日期范围选择        │  │
│            │  └─────────────────────────────────────┘  │
│  📰 领域事件 │                                           │
│    (45)    │  ┌─────────────────────────────────────┐  │
│            │  │ 📄 涨停报告_20260402.pdf    15页   │  │
│  ➕ 其他    │  │    2026-04-02 18:30    1.0MB  [查看]│  │
│            │  ├─────────────────────────────────────┤  │
│            │  │ 📄 涨停报告_20260401.pdf    12页   │  │
│            │  │    2026-04-01 18:25    0.9MB  [查看]│  │
│            │  ├─────────────────────────────────────┤  │
│            │  │ ...                                 │  │
│            │  └─────────────────────────────────────┘  │
│            │           [上一页] 1/7 [下一页]            │
└────────────┴────────────────────────────────────────────┘
```

### 5.2 PDF 阅读器弹窗
```
┌─────────────────────────────────────────────────────────┐
│  涨停报告_20260402.pdf                    [×] [⬇下载]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │                                                 │   │
│  │              PDF 内容预览区域                    │   │
│  │         (使用 pdf.js 或浏览器原生预览)           │   │
│  │                                                 │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [←] 第 5 / 15 页 [→]      [+] 放大 [-] 缩小           │
└─────────────────────────────────────────────────────────┘
```

---

## 6. 核心组件设计

### 6.1 ReportService（后端服务）
```python
class ReportService:
    """报告服务 - 管理报告元数据和文件"""
    
    def list_reports(self, report_type: str, page: int, page_size: int, 
                     start_date: date = None, end_date: date = None) -> dict:
        """获取报告列表（按时间倒序）"""
        pass
    
    def get_report(self, report_id: int) -> dict:
        """获取单个报告信息"""
        pass
    
    def save_report_metadata(self, report_type: str, report_name: str, 
                            report_date: date, file_path: str, 
                            file_size: int, page_count: int, params: dict) -> int:
        """保存报告元数据"""
        pass
    
    def delete_report(self, report_id: int, delete_file: bool = False) -> bool:
        """删除报告"""
        pass
    
    def get_file_path(self, report_id: int) -> str:
        """获取文件物理路径"""
        pass
```

### 6.2 ReportGenerator（报告生成器）
```python
class ReportGenerator(ABC):
    """报告生成器基类"""
    
    @abstractmethod
    def generate(self, report_date: date, params: dict) -> str:
        """生成报告，返回文件路径"""
        pass
    
    @abstractmethod
    def get_report_name(self, report_date: date) -> str:
        """生成报告文件名"""
        pass

class ZTReportGenerator(ReportGenerator):
    """涨停报告生成器"""
    pass

class EventReportGenerator(ReportGenerator):
    """领域事件报告生成器"""
    pass
```

### 6.3 ReportManager（前端管理器）
```javascript
class ReportManager extends EventEmitter {
    // 报告管理器 - 处理报告列表、分类、搜索
    
    async loadReportTypes() {}
    async loadReports(type, page, pageSize, filters) {}
    async viewReport(reportId) {}
    async downloadReport(reportId) {}
    async generateReport(type, date, params) {}
}
```

### 6.4 PDFViewer（PDF阅读器组件）
```javascript
class PDFViewer extends Component {
    // PDF 阅读器 - 使用 pdf.js 或 iframe 嵌入
    
    open(fileUrl, reportName) {}
    close() {}
    nextPage() {}
    prevPage() {}
    zoomIn() {}
    zoomOut() {}
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
│   │   │   ├── 涨停报告_20260401.pdf
│   │   │   ├── 涨停报告_20260402.pdf
│   │   │   └── ...
│   │   └── 03/
│   └── 2025/
├── event_report/                 # 领域事件报告
│   └── ...
└── temp/                         # 临时文件
```

### 7.2 命名规范
- 涨停报告：`涨停报告_YYYYMMDD.pdf`
- 领域事件报告：`领域事件报告_YYYYMMDD.pdf`
- 自定义报告：`{类型名称}_YYYYMMDD_{序号}.pdf`

---

## 8. 扩展性设计

### 8.1 新增报告类型步骤
1. **数据库**：在 `report_types` 表添加记录
2. **后端**：
   - 创建 `report/{type}/generator.py` 实现 `ReportGenerator`
   - 在 `ReportGeneratorFactory` 注册新类型
3. **前端**：无需修改，自动从 `/api/reports/types` 获取

### 8.2 报告生成触发方式
| 方式 | 说明 |
|------|------|
| 定时任务 | 每日收盘后自动生成 |
| 手动触发 | 前端点击"生成新报告" |
| API 调用 | 其他模块完成后触发 |

---

## 9. 安全考虑

1. **文件访问控制**：验证用户权限后才返回文件
2. **路径安全**：禁止访问 `../` 等非法路径
3. **文件类型限制**：只允许 `.pdf` 文件
4. **文件大小限制**：限制单文件最大 50MB

---

## 10. 开发计划

### Phase 1: 基础框架
- [ ] 数据库表创建
- [ ] ReportService 实现
- [ ] 基础 API 接口
- [ ] 前端页面框架

### Phase 2: 核心功能
- [ ] 报告列表展示
- [ ] PDF 预览功能
- [ ] 文件下载功能
- [ ] 报告搜索/筛选

### Phase 3: 报告生成
- [ ] ReportGenerator 基类
- [ ] 涨停报告生成器
- [ ] 领域事件报告生成器
- [ ] 生成任务管理

### Phase 4: 优化完善
- [ ] 分页优化
- [ ] 缓存策略
- [ ] 错误处理
- [ ] 性能优化

---

## 11. 待评审问题

1. **PDF 预览方案**：
   - 方案A：使用 pdf.js 前端渲染（推荐，体验好）
   - 方案B：浏览器原生预览（简单，依赖浏览器插件）
   - 方案C：后端转图片预览（兼容性好，资源消耗大）

2. **文件存储**：
   - 当前方案：本地文件系统
   - 备选方案：MinIO/OSS 对象存储（后续扩展）

3. **报告生成**：
   - 同步生成：简单，但大报告会阻塞
   - 异步生成：需要任务队列，体验好（推荐）

4. **权限控制**：
   - 当前：无权限控制
   - 需要：基于角色的访问控制？

请评审以上方案，提出修改意见后进入开发阶段。
