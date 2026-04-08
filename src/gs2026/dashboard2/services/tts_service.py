"""
TTS Service - Text to Speech using Edge TTS
"""
import logging
from pathlib import Path
from typing import Optional, Dict
import asyncio
import json
import hashlib

logger = logging.getLogger(__name__)

# Try to import edge_tts
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge_tts not available, TTS functionality disabled")


class TTSService:
    """TTS Service using Edge TTS"""
    
    # Available voices
    VOICES = {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",  # 女声，温和
        "xiaoyi": "zh-CN-XiaoyiNeural",      # 女声，活泼
        "yunjian": "zh-CN-YunjianNeural",    # 男声，新闻
        "yunxi": "zh-CN-YunxiNeural",        # 男声，温和
    }
    
    DEFAULT_VOICE = "xiaoxiao"
    DEFAULT_SPEED = 1.0
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path("G:/report/.tts_cache/audio")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir = cache_dir or Path("G:/report/.tts_cache")
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # PDF独立的缓存目录
        self.pdf_cache_dir = Path("G:/report/.tts_cache/by_pdf")
        self.pdf_cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_pdf_hash(self, pdf_path: Path) -> str:
        """获取PDF路径的哈希值"""
        return hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]
    
    def _get_pdf_cache_dir(self, pdf_path: Path) -> Path:
        """获取指定PDF的缓存目录"""
        pdf_hash = self._get_pdf_hash(pdf_path)
        pdf_dir = self.pdf_cache_dir / pdf_hash
        pdf_dir.mkdir(parents=True, exist_ok=True)
        return pdf_dir
    
    def get_audio_path(self, text: str, voice: str = None, pdf_path: Path = None) -> Path:
        """Get cache path for audio file
        
        Args:
            text: Text to synthesize
            voice: Voice to use
            pdf_path: Optional PDF path for PDF-independent caching
        """
        voice = voice or self.DEFAULT_VOICE
        
        if pdf_path:
            # PDF独立缓存：使用PDF路径+文本内容作为键
            pdf_dir = self._get_pdf_cache_dir(pdf_path)
            text_hash = hashlib.md5(text.encode()).hexdigest()
            return pdf_dir / f"{text_hash}_{voice}.mp3"
        else:
            # 向后兼容：纯文本哈希
            hash_key = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
            return self.cache_dir / f"{hash_key}.mp3"
    
    def get_metadata_path(self, text: str, voice: str = None, pdf_path: Path = None) -> Path:
        """Get cache path for metadata
        
        Args:
            text: Text to synthesize
            voice: Voice to use
            pdf_path: Optional PDF path for PDF-independent caching
        """
        voice = voice or self.DEFAULT_VOICE
        
        if pdf_path:
            # PDF独立缓存
            pdf_dir = self._get_pdf_cache_dir(pdf_path)
            text_hash = hashlib.md5(text.encode()).hexdigest()
            return pdf_dir / f"{text_hash}_{voice}.json"
        else:
            # 向后兼容
            hash_key = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
            return self.metadata_dir / f"{hash_key}.json"
    
    def is_cached(self, text: str, voice: str = None, pdf_path: Path = None) -> bool:
        """Check if audio is cached
        
        Args:
            text: Text to check
            voice: Voice to check
            pdf_path: Optional PDF path for PDF-independent caching
        """
        audio_path = self.get_audio_path(text, voice, pdf_path)
        meta_path = self.get_metadata_path(text, voice, pdf_path)
        return audio_path.exists() and meta_path.exists()
    
    def get_cached_info(self, text: str, voice: str = None, pdf_path: Path = None) -> Optional[Dict]:
        """Get cached audio info
        
        Args:
            text: Text to get info for
            voice: Voice to get info for
            pdf_path: Optional PDF path for PDF-independent caching
        """
        if not self.is_cached(text, voice, pdf_path):
            return None
        
        meta_path = self.get_metadata_path(text, voice, pdf_path)
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
            return None
    
    async def generate_async(self, text: str, voice: str = None, speed: float = None) -> Optional[Dict]:
        """
        Generate TTS audio asynchronously
        
        Returns:
            Dict with audio info or None on failure
        """
        if not EDGE_TTS_AVAILABLE:
            logger.error("edge_tts not available")
            return None
        
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        # Check cache
        if self.is_cached(text, voice):
            info = self.get_cached_info(text, voice)
            if info:
                return info
        
        try:
            # Get voice ID
            voice_id = self.VOICES.get(voice, self.VOICES[self.DEFAULT_VOICE])
            
            # Calculate rate (Edge TTS format: +10% or -10%)
            rate_pct = int((speed - 1) * 100)
            if rate_pct > 0:
                rate_str = f"+{rate_pct}%"
            elif rate_pct < 0:
                rate_str = f"{rate_pct}%"
            else:
                rate_str = "+0%"  # Default rate
            
            # Generate audio
            audio_path = self.get_audio_path(text, voice)
            communicate = edge_tts.Communicate(text, voice_id, rate=rate_str)
            await communicate.save(str(audio_path))
            
            # Get duration (approximate)
            duration = self._estimate_duration(text, speed)
            
            # Save metadata
            info = {
                "text": text,
                "voice": voice,
                "speed": speed,
                "audio_path": str(audio_path),
                "duration": duration,
                "file_size": audio_path.stat().st_size if audio_path.exists() else 0
            }
            
            meta_path = self.get_metadata_path(text, voice)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False)
            
            return info
            
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None
    
    def generate(self, text: str, voice: str = None, speed: float = None) -> Optional[Dict]:
        """Generate TTS audio (sync wrapper)"""
        try:
            return asyncio.run(self.generate_async(text, voice, speed))
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None
    
    def _estimate_duration(self, text: str, speed: float) -> float:
        """Estimate audio duration in seconds"""
        # Chinese: ~4 characters per second at normal speed
        char_count = len(text)
        duration = char_count / 4 / speed
        return max(1.0, duration)  # Minimum 1 second
    
    def generate_for_segments(self, segments: list, voice: str = None, speed: float = None, 
                              pregenerate: bool = False) -> dict:
        """
        Generate TTS for multiple segments
        
        Args:
            segments: List of segments with 'text' field
            voice: Voice to use
            speed: Speed multiplier
            pregenerate: If True, generate all audio synchronously (slow)
                        If False, only check cache and mark status
        
        Returns:
            Dict mapping text_hash to audio info (for frontend matching by hash)
        """
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        results = {}
        for i, segment in enumerate(segments):
            text = segment.get("text", "")
            if not text:
                continue
            
            text_hash = hashlib.md5(text.encode()).hexdigest()
            
            # Check if already cached
            if self.is_cached(text, voice):
                info = self.get_cached_info(text, voice)
                if info:
                    results[text_hash] = {
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                        "duration": info.get("duration", 0),
                        "ready": True
                    }
                else:
                    results[text_hash] = {
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                        "duration": 0,
                        "ready": False
                    }
            else:
                if pregenerate:
                    # Generate synchronously (slow but ensures audio exists)
                    try:
                        info = self.generate(text, voice, speed)
                        if info:
                            results[text_hash] = {
                                "text_hash": text_hash,
                                "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                                "duration": info.get("duration", 0),
                                "ready": True
                            }
                            logger.info(f"Pre-generated audio for segment {i}: {text[:30]}...")
                        else:
                            results[text_hash] = {
                                "text_hash": text_hash,
                                "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                                "duration": 0,
                                "ready": False
                            }
                    except Exception as e:
                        logger.error(f"Failed to pre-generate audio for segment {i}: {e}")
                        results[text_hash] = {
                            "text_hash": text_hash,
                            "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                            "duration": 0,
                            "ready": False
                        }
                else:
                    # Mark as not ready, will be generated on first play
                    results[text_hash] = {
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?text={text_hash}&voice={voice}",
                        "duration": 0,
                        "ready": False
                    }
        
        return results
    
    def ensure_audio(self, text: str, voice: str = None, speed: float = None) -> Optional[Dict]:
        """
        Ensure audio is generated (called when user clicks play)
        """
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        # Check cache first
        if self.is_cached(text, voice):
            return self.get_cached_info(text, voice)
        
        # Generate synchronously
        return self.generate(text, voice, speed)
    
    def get_audio_file(self, text_hash: str, voice: str = None) -> Optional[Path]:
        """Get audio file path by hash"""
        # Direct lookup by hash
        voice = voice or self.DEFAULT_VOICE
        
        # Try direct path first
        audio_path = self.cache_dir / f"{text_hash}.mp3"
        meta_path = self.metadata_dir / f"{text_hash}.json"
        
        if audio_path.exists() and meta_path.exists():
            return audio_path
        
        # Fallback: search through metadata files
        for meta_file in self.metadata_dir.glob("*.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    text = info.get("text", "")
                    stored_voice = info.get("voice", self.DEFAULT_VOICE)
                    if hashlib.md5(text.encode()).hexdigest() == text_hash and stored_voice == voice:
                        audio_path = Path(info.get("audio_path", ""))
                        if audio_path.exists():
                            return audio_path
            except Exception:
                continue
        
        return None
    
    def get_text_by_hash(self, text_hash: str) -> Optional[str]:
        """Get original text by hash"""
        # Try direct lookup
        meta_path = self.metadata_dir / f"{text_hash}.json"
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    return info.get("text", "")
            except Exception:
                pass
        
        # Fallback: search through metadata files
        for meta_file in self.metadata_dir.glob("*.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    text = info.get("text", "")
                    if hashlib.md5(text.encode()).hexdigest() == text_hash:
                        return text
            except Exception:
                continue
        
        return None
    
    # ==================== PDF独立缓存方法 ====================
    
    def generate_for_pdf(self, pdf_path: Path, segments: list, voice: str = None, 
                         speed: float = None, pregenerate: bool = False) -> dict:
        """
        为PDF生成TTS，每个PDF有独立的缓存
        
        Args:
            pdf_path: PDF文件路径
            segments: 分段列表，每个包含 'id' 和 'text'
            voice: 语音类型
            speed: 语速
            pregenerate: 是否预生成所有音频
        
        Returns:
            Dict: 分段索引到音频信息的映射
        """
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        results = {}
        pdf_hash = self._get_pdf_hash(pdf_path)
        
        for segment in segments:
            seg_index = segment.get("id", 0)
            text = segment.get("text", "")
            
            if not text:
                continue
            
            text_hash = hashlib.md5(text.encode()).hexdigest()
            
            # 检查PDF独立缓存
            if self.is_cached(text, voice, pdf_path):
                info = self.get_cached_info(text, voice, pdf_path)
                if info:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?pdf={pdf_hash}&seg={seg_index}&voice={voice}",
                        "duration": info.get("duration", 0),
                        "ready": True
                    }
                    continue
            
            # 需要生成
            if pregenerate:
                info = self._generate_for_pdf_segment(pdf_path, seg_index, text, voice, speed)
                if info:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?pdf={pdf_hash}&seg={seg_index}&voice={voice}",
                        "duration": info.get("duration", 0),
                        "ready": True
                    }
                else:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "text_hash": text_hash,
                        "audio_url": f"/api/reports/tts/audio?pdf={pdf_hash}&seg={seg_index}&voice={voice}",
                        "duration": 0,
                        "ready": False
                    }
            else:
                # 标记为未生成，按需生成
                results[str(seg_index)] = {
                    "segment_index": seg_index,
                    "text_hash": text_hash,
                    "audio_url": f"/api/reports/tts/audio?pdf={pdf_hash}&seg={seg_index}&voice={voice}",
                    "duration": 0,
                    "ready": False
                }
        
        return results
    
    def _generate_for_pdf_segment(self, pdf_path: Path, segment_index: int,
                                   text: str, voice: str, speed: float) -> Optional[Dict]:
        """为PDF的指定分段生成音频"""
        if not EDGE_TTS_AVAILABLE:
            logger.error("edge_tts not available")
            return None
        
        try:
            voice_id = self.VOICES.get(voice, self.VOICES[self.DEFAULT_VOICE])
            
            # 计算语速
            rate_pct = int((speed - 1) * 100)
            if rate_pct > 0:
                rate_str = f"+{rate_pct}%"
            elif rate_pct < 0:
                rate_str = f"{rate_pct}%"
            else:
                rate_str = "+0%"
            
            # 生成音频
            audio_path = self.get_audio_path(text, voice, pdf_path)
            communicate = edge_tts.Communicate(text, voice_id, rate=rate_str)
            asyncio.run(communicate.save(str(audio_path)))
            
            # 估算时长
            duration = self._estimate_duration(text, speed)
            
            # 保存元数据
            info = {
                "pdf_path": str(pdf_path),
                "segment_index": segment_index,
                "text": text,
                "text_hash": hashlib.md5(text.encode()).hexdigest(),
                "voice": voice,
                "speed": speed,
                "duration": duration,
                "audio_path": str(audio_path),
            }
            
            meta_path = self.get_metadata_path(text, voice, pdf_path)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False)
            
            logger.info(f"Generated audio for {pdf_path.name} segment {segment_index}: {duration:.2f}s")
            return info
            
        except Exception as e:
            logger.error(f"Failed to generate audio for {pdf_path.name} segment {segment_index}: {e}")
            return None
    
    def get_pdf_audio_file(self, pdf_hash: str, segment_index: int, 
                           voice: str = None) -> Optional[Path]:
        """通过PDF哈希和分段索引获取音频文件"""
        voice = voice or self.DEFAULT_VOICE
        
        # 查找PDF缓存目录
        pdf_dir = self.pdf_cache_dir / pdf_hash
        if not pdf_dir.exists():
            return None
        
        # 查找分段音频文件
        for audio_file in pdf_dir.glob(f"*_{voice}.mp3"):
            meta_file = audio_file.with_suffix('.json')
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                        if info.get("segment_index") == segment_index:
                            return audio_file
                except Exception:
                    continue
        
        return None
