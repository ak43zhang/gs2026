"""
Document Reader Service - 可扩展的文档阅读器基类
支持PDF、EPUB等格式，统一接口
"""
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Protocol, runtime_checkable
from abc import ABC, abstractmethod
import json
import hashlib

logger = logging.getLogger(__name__)


@runtime_checkable
class DocumentReader(Protocol):
    """文档阅读器接口协议"""
    
    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """返回支持的文件扩展名列表"""
        pass
    
    @abstractmethod
    def can_read(self, file_path: Path) -> bool:
        """检查是否支持读取该文件"""
        pass
    
    @abstractmethod
    def extract_text(self, file_path: Path, strategy: str = "original") -> List[Dict]:
        """提取文本并分段"""
        pass


class BaseDocumentReader(ABC):
    """文档阅读器基类 - 提供通用的分段逻辑"""
    
    # 分段策略常量
    STRATEGY_ORIGINAL = "original"
    STRATEGY_LINE = "line"
    STRATEGY_SMART = "smart"
    STRATEGY_STRICT_LINE = "strict_line"
    
    # 标题识别规则
    TITLE_PATTERNS = [
        r'^第[一二三四五六七八九十\d]+部分[：:]?',
        r'^第[一二三四五六七八九十\d]+章[：:]?',
        r'^第[一二三四五六七八九十\d]+节[：:]?',
        r'^\d+[\.、]\s*\S+[^。！？；\s]$',
        r'^(?:市场|板块|个股|资金|策略|风险|总结|展望|前言|结语|概况|分析|深度|复盘)[概况分析总结深度复盘]?[：:]?',
    ]
    
    # 数字格式化规则
    NUMBER_PATTERNS = [
        (r"(\d{4})-(\d{2})-(\d{2})", r"\1年\2月\3日"),
        (r"(\d{4})/(\d{2})/(\d{2})", r"\1年\2月\3日"),
        (r"(\d{1,2}):(\d{2}):(\d{2})", r"\1点\2分\3秒"),
        (r"(\d{1,2}):(\d{2})", r"\1点\2分"),
        (r"(\d+)\.(\d+)%", r"百分之\1点\2"),
        (r"(\d+)%", r"百分之\1"),
        (r"(\d{6})", r"代码\1"),
    ]
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "short_threshold": 15,
            "long_threshold": 60,
            "max_segment_len": 100,
            "format_numbers": True,
        }
    
    def _is_title_line(self, line: str) -> bool:
        """检测是否是标题行"""
        line = line.strip()
        if not line:
            return False
        for pattern in self.TITLE_PATTERNS:
            if re.match(pattern, line):
                return True
        return False
    
    def _format_for_tts(self, text: str) -> str:
        """格式化数字为口语化表达"""
        for pattern, replacement in self.NUMBER_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text
    
    def _calc_pause(self, text: str) -> float:
        """计算段落后停顿时长"""
        if not text:
            return 0.5
        if text.endswith('。'):
            return 0.8
        elif text.endswith('！') or text.endswith('？'):
            return 1.0
        elif text.endswith('；'):
            return 0.6
        elif text.endswith('，'):
            return 0.3
        return 0.5
    
    def _split_original(self, text: str) -> List[str]:
        """按句分割策略"""
        endings = ['。', '！', '？', '；']
        sentences = []
        lines = text.split('\n')
        current_sentence = ""
        prev_ends_with_number = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            is_title = self._is_title_line(line)
            is_number_prefix = bool(re.match(r'^[\d一二三四五六七八九十]+[\.、]\s*', line))
            ends_with_number = bool(re.search(r'[\d]+[\.、]\s*$', line))
            starts_with_star = line.startswith('*')
            
            if is_title:
                if current_sentence.strip():
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
                sentences.append(line)
                prev_ends_with_number = ends_with_number
                continue
            
            if prev_ends_with_number and starts_with_star and current_sentence:
                pass
            elif is_number_prefix and current_sentence:
                sentences.append(current_sentence.strip())
                current_sentence = ""
            
            if current_sentence:
                current_sentence += " " + line
            else:
                current_sentence = line
            
            prev_ends_with_number = ends_with_number
            
            if any(current_sentence.endswith(e) for e in endings):
                sentences.append(current_sentence.strip())
                current_sentence = ""
                prev_ends_with_number = False
        
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return sentences if sentences else [text]
    
    def _split_by_lines(self, text: str) -> List[str]:
        """按行分割策略"""
        lines = text.split('\n')
        result = []
        pending_line = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('*') and pending_line:
                pending_line = pending_line + line
                continue
            
            if line.startswith('*'):
                pending_line = line
                continue
            
            if pending_line:
                if len(pending_line) >= 3:
                    result.append(pending_line)
                pending_line = ""
            
            if len(line) >= 3:
                result.append(line)
        
        if pending_line and len(pending_line) >= 3:
            result.append(pending_line)
        
        return result if result else [text]
    
    def _split_strict_by_lines(self, text: str) -> List[str]:
        """严格逐行分割策略"""
        lines = text.split('\n')
        result = []
        pending_line = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('*') and pending_line:
                pending_line = pending_line + line
                continue
            
            if line.startswith('*'):
                pending_line = line
                continue
            
            if pending_line:
                result.append(pending_line)
                pending_line = ""
            
            result.append(line)
        
        if pending_line:
            result.append(pending_line)
        
        return result if result else [text]
    
    def _split_smart(self, text: str) -> List[str]:
        """智能分段策略"""
        raw_sentences = self._split_original(text)
        short_threshold = self.config.get("short_threshold", 15)
        max_len = self.config.get("max_segment_len", 100)
        
        segments = []
        buffer = ""
        
        for sent in raw_sentences:
            sent = sent.strip()
            if not sent:
                continue
            
            if len(sent) < short_threshold:
                buffer += sent
                if len(buffer) >= short_threshold:
                    segments.append(buffer)
                    buffer = ""
            else:
                if buffer:
                    segments.append(buffer + sent)
                    buffer = ""
                else:
                    segments.append(sent)
        
        if buffer:
            segments.append(buffer)
        
        return segments
    
    def _apply_strategy(self, text: str, strategy: str) -> List[str]:
        """应用分段策略"""
        if strategy == self.STRATEGY_LINE:
            return self._split_by_lines(text)
        elif strategy == self.STRATEGY_SMART:
            return self._split_smart(text)
        elif strategy == self.STRATEGY_STRICT_LINE:
            return self._split_strict_by_lines(text)
        else:
            return self._split_original(text)
    
    def get_cache_path(self, file_path: Path, strategy: str = "smart") -> Path:
        """获取缓存文件路径"""
        hash_key = hashlib.md5(f"{file_path}_{strategy}".encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"


class PDFReader(BaseDocumentReader):
    """PDF文档阅读器"""
    
    @property
    def supported_extensions(self) -> List[str]:
        return ['.pdf']
    
    def can_read(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.pdf'
    
    def extract_text(self, file_path: Path, strategy: str = "original") -> List[Dict]:
        """从PDF提取文本"""
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not available")
            return []
        
        cache_path = self.get_cache_path(file_path, strategy)
        
        # 检查缓存
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    logger.info(f"Using cached PDF content: {file_path}")
                    return cached.get('segments', [])
            except Exception as e:
                logger.warning(f"Cache read failed: {e}")
        
        segments = []
        try:
            with pdfplumber.open(file_path) as pdf:
                segment_id = 0
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    raw_segments = self._apply_strategy(text, strategy)
                    
                    if self.config.get("format_numbers", True):
                        raw_segments = [self._format_for_tts(s) for s in raw_segments]
                    
                    for seg_text in raw_segments:
                        seg_text = seg_text.strip()
                        if len(seg_text) < 2:
                            continue
                        
                        segments.append({
                            "id": segment_id,
                            "text": seg_text,
                            "page": page_num,
                            "type": strategy,
                            "pause_after": self._calc_pause(seg_text)
                        })
                        segment_id += 1
            
            # 保存缓存
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({'segments': segments, 'strategy': strategy}, f, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")
            
            return segments
            
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return []


class EPUBReader(BaseDocumentReader):
    """EPUB文档阅读器"""
    
    @property
    def supported_extensions(self) -> List[str]:
        return ['.epub']
    
    def can_read(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.epub'
    
    def extract_text(self, file_path: Path, strategy: str = "original") -> List[Dict]:
        """从EPUB提取文本"""
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
        except ImportError as e:
            logger.error(f"ebooklib or beautifulsoup4 not available: {e}")
            return []
        
        # 检查文件是否存在
        if not file_path.exists():
            logger.error(f"EPUB file not found: {file_path}")
            return []
        
        logger.info(f"Reading EPUB file: {file_path}, size: {file_path.stat().st_size} bytes")
        
        cache_path = self.get_cache_path(file_path, strategy)
        
        # 检查缓存
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    logger.info(f"Using cached EPUB content: {file_path}")
                    return cached.get('segments', [])
            except Exception as e:
                logger.warning(f"Cache read failed: {e}")
        
        segments = []
        try:
            logger.info(f"Opening EPUB: {file_path}")
            book = epub.read_epub(str(file_path))
            logger.info(f"EPUB opened successfully, title: {book.get_metadata('DC', 'title')}")
            
            segment_id = 0
            chapter_num = 0
            items_count = 0
            
            for item in book.get_items():
                items_count += 1
                try:
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        chapter_num += 1
                        logger.debug(f"Processing chapter {chapter_num}: {item.get_name()}")
                        
                        # 解析HTML内容
                        content = item.get_content()
                        if not content:
                            logger.warning(f"Empty content in chapter {chapter_num}")
                            continue
                        
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # 提取文本
                        text = soup.get_text(separator='\n')
                        text_len = len(text.strip())
                        logger.debug(f"Chapter {chapter_num} text length: {text_len}")
                        
                        if not text.strip():
                            continue
                        
                        # 应用分段策略
                        raw_segments = self._apply_strategy(text, strategy)
                        logger.debug(f"Chapter {chapter_num} split into {len(raw_segments)} segments")
                        
                        # 格式化数字
                        if self.config.get("format_numbers", True):
                            raw_segments = [self._format_for_tts(s) for s in raw_segments]
                        
                        for seg_text in raw_segments:
                            seg_text = seg_text.strip()
                            if len(seg_text) < 2:
                                continue
                            
                            segments.append({
                                "id": segment_id,
                                "text": seg_text,
                                "page": chapter_num,  # EPUB使用章节号代替页码
                                "type": strategy,
                                "pause_after": self._calc_pause(seg_text)
                            })
                            segment_id += 1
                except Exception as e:
                    logger.error(f"Error processing EPUB item {items_count}: {e}")
                    continue
            
            logger.info(f"EPUB processed: {items_count} items, {chapter_num} chapters, {len(segments)} segments")
            
            # 保存缓存
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({'segments': segments, 'strategy': strategy}, f, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")
            
            return segments
            
        except Exception as e:
            logger.error(f"Error extracting EPUB text: {e}")
            return []


class DocumentReaderFactory:
    """文档阅读器工厂 - 管理所有阅读器实例"""
    
    _readers: List[BaseDocumentReader] = []
    _initialized = False
    
    @classmethod
    def _initialize(cls):
        """初始化所有阅读器"""
        if cls._initialized:
            return
        
        cls._readers = [
            PDFReader(),
            EPUBReader(),
        ]
        cls._initialized = True
        logger.info(f"DocumentReaderFactory initialized with {len(cls._readers)} readers")
    
    @classmethod
    def get_reader(cls, file_path: Path) -> Optional[BaseDocumentReader]:
        """根据文件路径获取合适的阅读器"""
        cls._initialize()
        
        file_path = Path(file_path)
        for reader in cls._readers:
            if reader.can_read(file_path):
                return reader
        
        logger.warning(f"No reader found for file: {file_path}")
        return None
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """获取所有支持的文件扩展名"""
        cls._initialize()
        
        extensions = []
        for reader in cls._readers:
            extensions.extend(reader.supported_extensions)
        return extensions
    
    @classmethod
    def extract_text(cls, file_path: Path, strategy: str = "original") -> List[Dict]:
        """提取文本的便捷方法"""
        reader = cls.get_reader(file_path)
        if reader:
            return reader.extract_text(file_path, strategy)
        return []


# 向后兼容 - 保持原有接口
class PDFReaderService(PDFReader):
    """PDF阅读器服务 - 向后兼容"""
    pass


# 便捷函数
def extract_document_text(file_path: Path, strategy: str = "original") -> List[Dict]:
    """提取文档文本的便捷函数"""
    return DocumentReaderFactory.extract_text(file_path, strategy)
