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
    
    def get_audio_path(self, text: str, voice: str = None) -> Path:
        """Get cache path for audio file"""
        voice = voice or self.DEFAULT_VOICE
        hash_key = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.mp3"
    
    def get_metadata_path(self, text: str, voice: str = None) -> Path:
        """Get cache path for metadata"""
        voice = voice or self.DEFAULT_VOICE
        hash_key = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
        return self.metadata_dir / f"{hash_key}.json"
    
    def is_cached(self, text: str, voice: str = None) -> bool:
        """Check if audio is cached"""
        audio_path = self.get_audio_path(text, voice)
        meta_path = self.get_metadata_path(text, voice)
        return audio_path.exists() and meta_path.exists()
    
    def get_cached_info(self, text: str, voice: str = None) -> Optional[Dict]:
        """Get cached audio info"""
        if not self.is_cached(text, voice):
            return None
        
        meta_path = self.get_metadata_path(text, voice)
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
    
    def generate_for_segments(self, segments: list, voice: str = None, speed: float = None) -> list:
        """
        Generate TTS for multiple segments (async in background)
        
        Returns:
            List of segments with audio URLs (may be empty if not yet generated)
        """
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        results = []
        for segment in segments:
            text = segment.get("text", "")
            if not text:
                continue
            
            # Check if already cached
            if self.is_cached(text, voice):
                info = self.get_cached_info(text, voice)
                if info:
                    segment["audio_url"] = f"/api/reports/tts/audio?text={hashlib.md5(text.encode()).hexdigest()}&voice={voice}"
                    segment["duration"] = info.get("duration", 0)
                    segment["ready"] = True
                else:
                    segment["ready"] = False
            else:
                # Mark as not ready, will be generated on first play
                segment["ready"] = False
            
            # Always add audio_url for segments that will be generated
            segment["audio_url"] = f"/api/reports/tts/audio?text={hashlib.md5(text.encode()).hexdigest()}&voice={voice}"
            results.append(segment)
        
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
        # Find matching metadata
        voice = voice or self.DEFAULT_VOICE
        
        for meta_file in self.metadata_dir.glob("*.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    text = info.get("text", "")
                    if hashlib.md5(text.encode()).hexdigest() == text_hash:
                        audio_path = Path(info.get("audio_path", ""))
                        if audio_path.exists():
                            return audio_path
            except Exception:
                continue
        
        return None
