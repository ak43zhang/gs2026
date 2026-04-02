"""
PDF 阅读器服务
提取 PDF 文本并生成语音
"""
import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional
import re


class PDFReaderService:
    """PDF 阅读服务"""
    
    def __init__(self, tts_service, cache_dir: Path):
        self.tts_service = tts_service
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_text(self, pdf_path: str, max_pages: int = None) -> str:
        """
        从 PDF 提取文本
        
        Args:
            pdf_path: PDF 文件路径
            max_pages: 最大提取页数，None 表示全部
        
        Returns:
            提取的文本内容
        """
        text_parts = []
        
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
            
            for i, page in enumerate(pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"第{i}页。{page_text}")
        
        return '\n\n'.join(text_parts)
    
    def extract_text_by_pages(self, pdf_path: str) -> List[Dict]:
        """
        按页提取 PDF 文本
        
        Args:
            pdf_path: PDF 文件路径
        
        Returns:
            每页的文本列表 [{page_num, text}]
        """
        pages_text = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    pages_text.append({
                        'page_num': i,
                        'text': page_text,
                        'char_count': len(page_text)
                    })
        
        return pages_text
    
    def get_summary(self, pdf_path: str) -> Dict:
        """
        获取 PDF 摘要信息
        
        Args:
            pdf_path: PDF 文件路径
        
        Returns:
            摘要信息
        """
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            
            # 提取第一页作为预览
            first_page_text = pdf.pages[0].extract_text() if total_pages > 0 else ''
            
            # 提取所有文本统计
            total_chars = 0
            for page in pdf.pages:
                text = page.extract_text() or ''
                total_chars += len(text)
            
            return {
                'total_pages': total_pages,
                'total_chars': total_chars,
                'preview': first_page_text[:500] if first_page_text else '',
                'estimated_reading_time': total_chars // 250  # 约 250 字/分钟
            }
    
    def generate_audio(self, pdf_path: str, voice: str = 'xiaoxiao', 
                       speed: float = 1.0, max_pages: int = None) -> Dict:
        """
        为 PDF 生成语音
        
        Args:
            pdf_path: PDF 文件路径
            voice: 音色
            speed: 语速
            max_pages: 最大页数
        
        Returns:
            {audio_path, duration, text_length, pages}
        """
        pdf_path = Path(pdf_path)
        
        # 提取文本
        text = self.extract_text(str(pdf_path), max_pages)
        
        if not text.strip():
            raise ValueError('PDF 没有可提取的文本内容')
        
        # 清理文本（移除多余空格和特殊字符）
        text = self._clean_text(text)
        
        # 生成音频文件路径
        audio_filename = f"{pdf_path.stem}_read.mp3"
        audio_path = self.cache_dir / audio_filename
        
        # 生成语音
        result = self.tts_service.generate(text, audio_path, voice, speed)
        
        return {
            'audio_path': str(audio_path),
            'audio_url': f"/api/reports/audio/{audio_filename}",
            'duration': result['duration'],
            'text_length': len(text),
            'pages': max_pages or 'all'
        }
    
    def _clean_text(self, text: str) -> str:
        """清理文本内容"""
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊字符
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)
        # 移除页眉页脚常见的短横线
        text = re.sub(r'[-_]{3,}', '', text)
        return text.strip()
    
    def get_audio_status(self, pdf_path: str) -> Dict:
        """
        检查 PDF 是否已有生成的音频
        
        Args:
            pdf_path: PDF 文件路径
        
        Returns:
            音频状态
        """
        pdf_path = Path(pdf_path)
        audio_filename = f"{pdf_path.stem}_read.mp3"
        audio_path = self.cache_dir / audio_filename
        
        if audio_path.exists():
            stat = audio_path.stat()
            return {
                'exists': True,
                'audio_path': str(audio_path),
                'audio_url': f"/api/reports/audio/{audio_filename}",
                'file_size': stat.st_size,
                'created_at': stat.st_mtime
            }
        
        return {'exists': False}


# 同步包装器
class SyncPDFReaderService:
    """同步 PDF 阅读服务"""
    
    def __init__(self, tts_service, cache_dir: Path):
        self.async_service = PDFReaderService(tts_service, cache_dir)
    
    def extract_text(self, pdf_path: str, max_pages: int = None) -> str:
        return self.async_service.extract_text(pdf_path, max_pages)
    
    def extract_text_by_pages(self, pdf_path: str) -> List[Dict]:
        return self.async_service.extract_text_by_pages(pdf_path)
    
    def get_summary(self, pdf_path: str) -> Dict:
        return self.async_service.get_summary(pdf_path)
    
    def generate_audio(self, pdf_path: str, voice: str = 'xiaoxiao',
                       speed: float = 1.0, max_pages: int = None) -> Dict:
        return self.async_service.generate_audio(pdf_path, voice, speed, max_pages)
    
    def get_audio_status(self, pdf_path: str) -> Dict:
        return self.async_service.get_audio_status(pdf_path)
