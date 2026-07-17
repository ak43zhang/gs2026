# 报告中心EPUB格式支持设计文档

## 概述

为报告中心增加EPUB电子书格式支持，采用可扩展架构，便于后续增加其他文档类型。

## 架构设计

### 核心组件

```
DocumentReader (Protocol)
    ↑
BaseDocumentReader (ABC)
    ↑
    ├── PDFReader
    └── EPUBReader

DocumentReaderFactory
    ├── 自动注册所有阅读器
    └── 根据文件扩展名返回对应阅读器
```

### 类图

```
┌─────────────────────────────────────┐
│         DocumentReader              │
│         (Protocol)                  │
├─────────────────────────────────────┤
│ + can_read(file_path) -> bool       │
│ + extract_text(file_path, strategy) │
│   -> List[str]                      │
└─────────────────────────────────────┘
                  ↑
┌─────────────────────────────────────┐
│      BaseDocumentReader             │
│         (ABC)                       │
├─────────────────────────────────────┤
│ # _get_cache_path() -> str          │
│ # _get_file_hash() -> str           │
│ # _split_sentences() -> List[str]   │
│ + extract_text() -> List[str]       │
└─────────────────────────────────────┘
                  ↑
        ┌─────────┴─────────┐
        ↓                   ↓
┌───────────────┐   ┌───────────────┐
│   PDFReader   │   │  EPUBReader   │
├───────────────┤   ├───────────────┤
│+ _extract_    │   │+ _extract_    │
│  from_pdf()   │   │  from_epub()  │
│+ _get_page_   │   │+ _get_chapter_│
│  count()      │   │  count()      │
└───────────────┘   └───────────────┘
```

## 接口设计

### DocumentReader Protocol
```python
from typing import Protocol, List

class DocumentReader(Protocol):
    """文档阅读器协议"""
    
    def can_read(self, file_path: str) -> bool:
        """检查是否支持该文件格式"""
        ...
    
    def extract_text(self, file_path: str, strategy: str = 'original') -> List[str]:
        """提取文本并分段"""
        ...
```

### BaseDocumentReader
```python
from abc import ABC, abstractmethod

class BaseDocumentReader(ABC):
    """文档阅读器基类"""
    
    SUPPORTED_EXTENSIONS = []
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir
    
    def can_read(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS
    
    @abstractmethod
    def _extract_content(self, file_path: str) -> str:
        """子类实现具体提取逻辑"""
        pass
```

## 实现细节

### PDFReader
```python
class PDFReader(BaseDocumentReader):
    SUPPORTED_EXTENSIONS = ['.pdf']
    
    def _extract_content(self, file_path: str) -> str:
        import fitz
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    
    def _get_page_count(self, file_path: str) -> int:
        import fitz
        doc = fitz.open(file_path)
        return len(doc)
```

### EPUBReader
```python
class EPUBReader(BaseDocumentReader):
    SUPPORTED_EXTENSIONS = ['.epub']
    
    def _extract_content(self, file_path: str) -> str:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
        
        book = epub.read_epub(file_path)
        text = ""
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text += soup.get_text()
        return text
    
    def get_chapters(self, file_path: str) -> List[Dict]:
        """获取章节列表"""
        book = epub.read_epub(file_path)
        chapters = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                chapters.append({
                    'id': item.get_id(),
                    'title': self._extract_title(item),
                    'content': item.get_content()
                })
        return chapters
```

## 工厂模式

```python
class DocumentReaderFactory:
    """文档阅读器工厂"""
    
    _readers: List[BaseDocumentReader] = []
    
    @classmethod
    def register(cls, reader: BaseDocumentReader):
        """注册阅读器"""
        cls._readers.append(reader)
    
    @classmethod
    def get_reader(cls, file_path: str) -> Optional[BaseDocumentReader]:
        """获取支持该文件的阅读器"""
        for reader in cls._readers:
            if reader.can_read(file_path):
                return reader
        return None
    
    @classmethod
    def auto_register(cls):
        """自动注册所有阅读器"""
        cls.register(PDFReader())
        cls.register(EPUBReader())
```

## 缓存机制

### 缓存路径
```
{cache_dir}/{md5_hash}.json
```

### 缓存内容
```json
{
  "file_path": "/path/to/file.pdf",
  "strategy": "original",
  "segments": ["段落1", "段落2", ...],
  "timestamp": 1234567890
}
```

### 哈希计算
```python
def _get_file_hash(self, file_path: str, strategy: str) -> str:
    content = f"{file_path}_{strategy}"
    return hashlib.md5(content.encode()).hexdigest()
```

## 分段策略

所有格式共享相同的分段策略：

| 策略 | 说明 |
|------|------|
| original | 按句分割（默认） |
| line | 按行分割 |
| smart | 智能合并短句 |
| strict_line | 严格逐行，不合并 |

## EPUB特殊功能

### 1. 章节导航
```python
def get_chapters(self, file_path: str) -> List[Dict]:
    """获取章节列表用于导航"""
    chapters = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            chapters.append({
                'id': item.get_id(),
                'title': self._extract_title(item),
                'order': len(chapters) + 1
            })
    return chapters
```

### 2. 图片预览
```python
def extract_images(self, file_path: str) -> List[Dict]:
    """提取图片转为base64"""
    images = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            images.append({
                'id': item.get_id(),
                'mime': item.get_media_type(),
                'data': base64.b64encode(item.get_content()).decode()
            })
    return images
```

## 路由集成

```python
@report_bp.route('/preview')
def preview_report():
    file_path = request.args.get('file')
    reader = DocumentReaderFactory.get_reader(file_path)
    
    if not reader:
        return jsonify({'error': '不支持的文件格式'}), 400
    
    if file_path.endswith('.epub'):
        chapters = reader.get_chapters(file_path)
        return jsonify({
            'type': 'epub',
            'chapters': chapters
        })
    else:
        segments = reader.extract_text(file_path)
        return jsonify({
            'type': 'pdf',
            'segments': segments
        })
```

## 依赖

```
ebooklib>=0.18
beautifulsoup4>=4.9.0
PyMuPDF>=1.23.0
```

## 向后兼容

- `PDFReaderService`作为`PDFReader`的别名保留
- 原有PDF功能完全不受影响
- 新格式通过工厂模式自动识别

## 扩展指南

添加新格式步骤：
1. 创建`XXXReader`类继承`BaseDocumentReader`
2. 设置`SUPPORTED_EXTENSIONS`
3. 实现`_extract_content()`方法
4. 在工厂中注册：`DocumentReaderFactory.register(XXXReader())`

---

*设计时间: 2026-04-08*
