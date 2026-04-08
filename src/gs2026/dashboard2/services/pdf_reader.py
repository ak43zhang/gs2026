"""
PDF Reader Service - Extract text from PDF and generate TTS
支持三种分段策略：original（原始）/ line（按行）/ smart（智能）
"""
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional
import json
import hashlib

logger = logging.getLogger(__name__)

# Try to import pdfplumber
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not available, PDF text extraction disabled")


class PDFReaderService:
    """PDF Reader - Extract text and prepare for TTS with smart segmentation"""
    
    # 分段策略
    STRATEGY_ORIGINAL = "original"  # 原始按句子分割
    STRATEGY_LINE = "line"          # 按行分割
    STRATEGY_SMART = "smart"        # 智能分段（推荐）
    STRATEGY_STRICT_LINE = "strict_line"  # 严格逐行（不合并、不过滤）
    
    # 默认配置
    DEFAULT_CONFIG = {
        "short_threshold": 15,      # 短句阈值（小于此值合并）
        "long_threshold": 60,       # 长句阈值（大于此值分割）
        "max_segment_len": 100,     # 最大段长度
        "format_numbers": True,     # 是否格式化数字
    }
    
    # 标题识别规则（用于无标点标题独立成行）
    TITLE_PATTERNS = [
        # 第X部分/章/节
        r'^第[一二三四五六七八九十\d]+部分[：:]?',
        r'^第[一二三四五六七八九十\d]+章[：:]?',
        r'^第[一二三四五六七八九十\d]+节[：:]?',
        # 数字序号 + 标题（无结束标点）
        r'^\d+[\.、]\s*\S+[^。！？；\s]$',
        # 常见标题关键词
        r'^(?:市场|板块|个股|资金|策略|风险|总结|展望|前言|结语|概况|分析|深度|复盘)[概况分析总结深度复盘]?[：:]?',
    ]
    
    # 数字格式化规则
    NUMBER_PATTERNS = [
        # 日期格式 2026-04-07 / 2026/04/07
        (r"(\d{4})-(\d{2})-(\d{2})", r"\1年\2月\3日"),
        (r"(\d{4})/(\d{2})/(\d{2})", r"\1年\2月\3日"),
        # 时间格式 10:30 / 10:30:00
        (r"(\d{1,2}):(\d{2}):(\d{2})", r"\1点\2分\3秒"),
        (r"(\d{1,2}):(\d{2})", r"\1点\2分"),
        # 百分比 5.5% / 5%
        (r"(\d+)\.(\d+)%", r"百分之\1点\2"),
        (r"(\d+)%", r"百分之\1"),
    ]
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path("G:/report/.tts_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config = self.DEFAULT_CONFIG.copy()
    
    def set_config(self, config: Dict):
        """更新配置"""
        self.config.update(config)
    
    def extract_text(self, pdf_path: Path, strategy: str = "smart") -> List[Dict]:
        """
        Extract text from PDF with specified segmentation strategy
        
        Args:
            pdf_path: PDF文件路径
            strategy: 分段策略 - original/line/smart
        
        Returns:
            List of text segments with metadata
        """
        if not PDFPLUMBER_AVAILABLE:
            return []
        
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return []
        
        try:
            segments = []
            segment_id = 0
            
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    # 根据策略分段
                    if strategy == self.STRATEGY_LINE:
                        raw_segments = self._split_by_lines(text)
                    elif strategy == self.STRATEGY_SMART:
                        raw_segments = self._split_smart(text)
                    elif strategy == self.STRATEGY_STRICT_LINE:
                        raw_segments = self._split_strict_by_lines(text)
                    else:  # original
                        raw_segments = self._split_original(text)
                    
                    # 格式化数字
                    if self.config.get("format_numbers", True):
                        raw_segments = [self._format_for_tts(s) for s in raw_segments]
                    
                    # 构建segment对象
                    for seg_text in raw_segments:
                        seg_text = seg_text.strip()
                        if len(seg_text) < 3:  # 过滤太短的
                            continue
                        
                        segments.append({
                            "id": segment_id,
                            "text": seg_text,
                            "page": page_num,
                            "type": strategy,
                            "pause_after": self._calc_pause(seg_text)
                        })
                        segment_id += 1
            
            return segments
            
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return []
    
    def _is_title_line(self, line: str) -> bool:
        """检测是否是标题行（无标点，应独立成行）"""
        line = line.strip()
        if not line:
            return False
        
        # 检查是否匹配标题规则
        for pattern in self.TITLE_PATTERNS:
            if re.match(pattern, line):
                return True
        
        return False
    
    def _split_original(self, text: str) -> List[str]:
        """原始策略：按中文标点分割句子，同时处理换行、序号和标题"""
        # 只使用中文标点作为句子结束符，避免英文句号导致的问题
        endings = ['。', '！', '？', '；']
        sentences = []
        
        # 先按行分割，处理每行
        lines = text.split('\n')
        current_sentence = ""
        prev_ends_with_number = False  # 上一行是否以数字序号结尾
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # 检测是否是标题行（应独立成行）
            is_title = self._is_title_line(line)
            
            # 检测是否是序号行（如 "1."、"2."、"(1)"、"①" 等）
            is_number_prefix = bool(re.match(r'^[\d一二三四五六七八九十]+[\.、]\s*', line))
            # 检测行尾的数字序号（如 "第二部分：重点个股深度分析 1."）
            ends_with_number = bool(re.search(r'[\d]+[\.、]\s*$', line))
            # 检测是否以 * 开头（如 *ST赛隆）
            starts_with_star = line.startswith('*')
            
            # 如果是标题行，独立成行
            if is_title:
                # 先保存之前的累积内容
                if current_sentence.strip():
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
                # 标题独立成行
                sentences.append(line)
                prev_ends_with_number = ends_with_number
                continue
            
            # 如果上一行以数字序号结尾，且当前行以*开头，强制合并
            if prev_ends_with_number and starts_with_star and current_sentence:
                # 继续累积，不保存
                pass
            # 如果当前行是序号（行首），且已有累积的句子，先保存
            elif is_number_prefix and current_sentence:
                sentences.append(current_sentence.strip())
                current_sentence = ""
            
            # 将当前行添加到当前句子
            if current_sentence:
                current_sentence += " " + line
            else:
                current_sentence = line
            
            # 记录当前行是否以数字序号结尾
            prev_ends_with_number = ends_with_number
            
            # 检查是否以结束符结尾
            if any(current_sentence.endswith(e) for e in endings):
                sentences.append(current_sentence.strip())
                current_sentence = ""
                prev_ends_with_number = False
        
        # 处理剩余的句子
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
            
            # 处理以 * 开头的行（如 *ST赛隆），与前一行合并
            if line.startswith('*') and pending_line:
                pending_line = pending_line + line
                continue
            
            # 如果当前行以 * 开头，暂存等待合并
            if line.startswith('*'):
                pending_line = line
                continue
            
            # 保存之前的待处理行
            if pending_line:
                if len(pending_line) >= 3:
                    result.append(pending_line)
                pending_line = ""
            
            # 处理当前行
            if len(line) >= 3:
                result.append(line)
        
        # 处理最后的待处理行
        if pending_line and len(pending_line) >= 3:
            result.append(pending_line)
        
        return result if result else [text]
    
    def _split_strict_by_lines(self, text: str) -> List[str]:
        """
        严格逐行分割策略 - 确保每一行都独立，不合并、不过滤
        适用于需要逐字逐行阅读的场景
        但会将 *ST 开头的行与前一行合并
        """
        lines = text.split('\n')
        result = []
        pending_line = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 处理以 * 开头的行（如 *ST赛隆），与前一行合并
            if line.startswith('*') and pending_line:
                pending_line = pending_line + line
                continue
            
            # 如果当前行以 * 开头，暂存等待合并
            if line.startswith('*'):
                pending_line = line
                continue
            
            # 保存之前的待处理行
            if pending_line:
                result.append(pending_line)
                pending_line = ""
            
            # 处理当前行
            result.append(line)
        
        # 处理最后的待处理行
        if pending_line:
            result.append(pending_line)
        
        return result if result else [text]
    
    def _split_smart(self, text: str) -> List[str]:
        """
        智能分段策略：
        1. 基础分句（按标点）
        2. 短句合并（避免碎片化）
        3. 长句保持（一口气读完）
        """
        # Step 1: 基础分句
        raw_sentences = self._split_original(text)
        
        short_threshold = self.config.get("short_threshold", 15)
        max_len = self.config.get("max_segment_len", 100)
        
        # Step 2: 短句合并
        segments = []
        buffer = ""
        
        for sent in raw_sentences:
            sent = sent.strip()
            if not sent:
                continue
            
            # 如果当前句子很短，累积到buffer
            if len(sent) < short_threshold:
                buffer += sent
                # 如果buffer已经够长，输出
                if len(buffer) >= short_threshold:
                    segments.append(buffer)
                    buffer = ""
            else:
                # 长句，先输出buffer，再输出当前句
                if buffer:
                    segments.append(buffer + sent)
                    buffer = ""
                else:
                    segments.append(sent)
        
        # 处理剩余buffer
        if buffer:
            segments.append(buffer)
        
        # Step 3: 超长句分割（按逗号）
        final_segments = []
        for seg in segments:
            if len(seg) > max_len:
                parts = self._split_by_comma(seg, max_len)
                final_segments.extend(parts)
            else:
                final_segments.append(seg)
        
        return final_segments if final_segments else [text]
    
    def _split_by_comma(self, text: str, max_len: int = 50) -> List[str]:
        """按逗号分割长句"""
        parts = []
        current = ""
        
        # 按逗号、分号分割
        delimiters = ['，', ',', '；', ';']
        
        for char in text:
            current += char
            if char in delimiters and len(current) >= max_len // 2:
                parts.append(current.strip())
                current = ""
        
        if current.strip():
            parts.append(current.strip())
        
        return parts if parts else [text]
    
    def _format_for_tts(self, text: str) -> str:
        """格式化数字为口语化表达"""
        # 应用所有数字格式化规则
        for pattern, replacement in self.NUMBER_PATTERNS:
            text = re.sub(pattern, replacement, text)
        
        # 格式化股票代码（6位数字，前面加"代码"）
        text = re.sub(r"(?<![\d年])\b(\d{6})\b", r"代码\1", text)
        
        return text
    
    def _calc_pause(self, text: str) -> float:
        """计算段落后停顿时长（秒）"""
        if not text:
            return 0.5
        
        # 根据结尾标点确定停顿（只使用中文标点）
        if text.endswith('。'):
            return 0.8
        elif text.endswith('！') or text.endswith('？'):
            return 1.0
        elif text.endswith('；'):
            return 0.6
        elif text.endswith('，'):
            return 0.3
        else:
            return 0.5
    
    def get_cache_path(self, pdf_path: Path, strategy: str = "smart") -> Path:
        """Get cache file path for PDF text"""
        hash_key = hashlib.md5(f"{pdf_path}_{strategy}".encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"
    
    def get_cached_text(self, pdf_path: Path, strategy: str = "smart") -> Optional[List[Dict]]:
        """Get cached text if available"""
        cache_path = self.get_cache_path(pdf_path, strategy)
        
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        
        return None
    
    def cache_text(self, pdf_path: Path, segments: List[Dict], strategy: str = "smart"):
        """Cache extracted text"""
        cache_path = self.get_cache_path(pdf_path, strategy)
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def extract_and_cache(self, pdf_path: Path, strategy: str = "smart") -> List[Dict]:
        """Extract text and cache it"""
        # Try cache first
        cached = self.get_cached_text(pdf_path, strategy)
        if cached:
            return cached
        
        # Extract fresh
        segments = self.extract_text(pdf_path, strategy)
        
        # Cache if successful
        if segments:
            self.cache_text(pdf_path, segments, strategy)
        
        return segments
    
    def clear_cache(self, pdf_path: Path = None):
        """Clear cache for specific PDF or all"""
        try:
            if pdf_path:
                for strategy in [self.STRATEGY_ORIGINAL, self.STRATEGY_LINE, self.STRATEGY_SMART]:
                    cache_path = self.get_cache_path(pdf_path, strategy)
                    if cache_path.exists():
                        cache_path.unlink()
            else:
                # Clear all cache
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")
