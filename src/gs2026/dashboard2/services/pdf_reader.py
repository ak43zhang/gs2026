"""
PDF Reader Service - Extract text from PDF and generate TTS
"""
import logging
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
    """PDF Reader - Extract text and prepare for TTS"""
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path("G:/report/.tts_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_text(self, pdf_path: Path) -> List[Dict]:
        """
        Extract text from PDF with paragraph/line structure
        
        Returns:
            List of text segments with metadata
            [
                {
                    "id": 0,
                    "text": "paragraph text",
                    "page": 1,
                    "type": "paragraph"
                }
            ]
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
                    
                    # Split by paragraphs (double newline)
                    paragraphs = text.split('\n\n')
                    
                    for para in paragraphs:
                        para = para.strip()
                        if not para:
                            continue
                        
                        # Further split long paragraphs into sentences
                        sentences = self._split_sentences(para)
                        
                        for sentence in sentences:
                            sentence = sentence.strip()
                            if len(sentence) < 5:  # Skip very short segments
                                continue
                            
                            segments.append({
                                "id": segment_id,
                                "text": sentence,
                                "page": page_num,
                                "type": "sentence"
                            })
                            segment_id += 1
            
            return segments
            
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return []
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences (Chinese-aware)"""
        # Chinese sentence endings
        endings = ['。', '！', '？', '.', '!', '?']
        sentences = []
        current = ""
        
        for char in text:
            current += char
            if char in endings:
                sentences.append(current.strip())
                current = ""
        
        if current.strip():
            sentences.append(current.strip())
        
        # If no sentences found, return whole text
        if not sentences:
            sentences = [text]
        
        return sentences
    
    def get_cache_path(self, pdf_path: Path) -> Path:
        """Get cache file path for PDF text"""
        # Create hash of PDF path
        hash_key = hashlib.md5(str(pdf_path).encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"
    
    def get_cached_text(self, pdf_path: Path) -> Optional[List[Dict]]:
        """Get cached text if available"""
        cache_path = self.get_cache_path(pdf_path)
        
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        
        return None
    
    def cache_text(self, pdf_path: Path, segments: List[Dict]):
        """Cache extracted text"""
        cache_path = self.get_cache_path(pdf_path)
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def extract_and_cache(self, pdf_path: Path) -> List[Dict]:
        """Extract text and cache it"""
        # Try cache first
        cached = self.get_cached_text(pdf_path)
        if cached:
            return cached
        
        # Extract fresh
        segments = self.extract_text(pdf_path)
        
        # Cache if successful
        if segments:
            self.cache_text(pdf_path, segments)
        
        return segments
