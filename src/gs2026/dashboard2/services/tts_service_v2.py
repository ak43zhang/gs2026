#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS Service V2 - PDF独立的语音缓存系统

核心改进：
1. 每个PDF有独立的缓存目录
2. 分段音频使用 pdf_path + segment_index 作为唯一标识
3. 支持按PDF清理缓存
4. 保持向后兼容
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List
import asyncio
import json
import hashlib
import shutil

logger = logging.getLogger(__name__)

# Try to import edge_tts
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge_tts not available, TTS functionality disabled")


class TTSServiceV2:
    """TTS Service with PDF-independent caching"""
    
    # Available voices
    VOICES = {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "xiaoyi": "zh-CN-XiaoyiNeural",
        "yunjian": "zh-CN-YunjianNeural",
        "yunxi": "zh-CN-YunxiNeural",
    }
    
    DEFAULT_VOICE = "xiaoxiao"
    DEFAULT_SPEED = 1.0
    
    def __init__(self, base_cache_dir: Path = None):
        """
        Initialize TTS Service V2
        
        Args:
            base_cache_dir: Base directory for all caches
        """
        self.base_cache_dir = base_cache_dir or Path("G:/report/.tts_cache")
        self.base_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录结构
        self.audio_dir = self.base_cache_dir / "audio"
        self.audio_dir.mkdir(exist_ok=True)
        
        self.metadata_dir = self.base_cache_dir / "metadata"
        self.metadata_dir.mkdir(exist_ok=True)
        
        # PDF独立的缓存根目录
        self.pdf_cache_dir = self.base_cache_dir / "by_pdf"
        self.pdf_cache_dir.mkdir(exist_ok=True)
    
    def _get_pdf_cache_dir(self, pdf_path: Path) -> Path:
        """获取指定PDF的缓存目录"""
        # 使用PDF路径的MD5作为目录名
        pdf_hash = hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]
        pdf_dir = self.pdf_cache_dir / pdf_hash
        pdf_dir.mkdir(parents=True, exist_ok=True)
        return pdf_dir
    
    def _get_segment_audio_path(self, pdf_path: Path, segment_index: int, 
                                 voice: str = None) -> Path:
        """获取分段音频的缓存路径"""
        voice = voice or self.DEFAULT_VOICE
        pdf_dir = self._get_pdf_cache_dir(pdf_path)
        return pdf_dir / f"segment_{segment_index:04d}_{voice}.mp3"
    
    def _get_segment_metadata_path(self, pdf_path: Path, segment_index: int,
                                    voice: str = None) -> Path:
        """获取分段元数据的缓存路径"""
        voice = voice or self.DEFAULT_VOICE
        pdf_dir = self._get_pdf_cache_dir(pdf_path)
        return pdf_dir / f"segment_{segment_index:04d}_{voice}.json"
    
    def is_segment_cached(self, pdf_path: Path, segment_index: int,
                          voice: str = None) -> bool:
        """检查指定PDF的指定分段是否已缓存"""
        voice = voice or self.DEFAULT_VOICE
        audio_path = self._get_segment_audio_path(pdf_path, segment_index, voice)
        meta_path = self._get_segment_metadata_path(pdf_path, segment_index, voice)
        return audio_path.exists() and meta_path.exists()
    
    def get_segment_info(self, pdf_path: Path, segment_index: int,
                         voice: str = None) -> Optional[Dict]:
        """获取指定分段的缓存信息"""
        voice = voice or self.DEFAULT_VOICE
        if not self.is_segment_cached(pdf_path, segment_index, voice):
            return None
        
        meta_path = self._get_segment_metadata_path(pdf_path, segment_index, voice)
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read segment metadata: {e}")
            return None
    
    async def generate_segment_async(self, pdf_path: Path, segment_index: int,
                                     text: str, voice: str = None,
                                     speed: float = None) -> Optional[Dict]:
        """为指定PDF的指定分段生成音频"""
        if not EDGE_TTS_AVAILABLE:
            logger.error("edge_tts not available")
            return None
        
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        # 检查是否已缓存
        if self.is_segment_cached(pdf_path, segment_index, voice):
            logger.info(f"Using cached audio for {pdf_path.name} segment {segment_index}")
            return self.get_segment_info(pdf_path, segment_index, voice)
        
        # 生成音频
        voice_id = self.VOICES.get(voice, self.VOICES[self.DEFAULT_VOICE])
        
        # 计算语速参数
        rate_pct = int((speed - 1.0) * 100)
        if rate_pct > 0:
            rate_str = f"+{rate_pct}%"
        elif rate_pct < 0:
            rate_str = f"{rate_pct}%"
        else:
            rate_str = "+0%"
        
        try:
            audio_path = self._get_segment_audio_path(pdf_path, segment_index, voice)
            communicate = edge_tts.Communicate(text, voice_id, rate=rate_str)
            await communicate.save(str(audio_path))
            
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
            
            meta_path = self._get_segment_metadata_path(pdf_path, segment_index, voice)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Generated audio for {pdf_path.name} segment {segment_index}: {duration:.2f}s")
            return info
            
        except Exception as e:
            logger.error(f"Failed to generate audio for {pdf_path.name} segment {segment_index}: {e}")
            return None
    
    def generate_segment(self, pdf_path: Path, segment_index: int,
                         text: str, voice: str = None,
                         speed: float = None) -> Optional[Dict]:
        """同步包装器"""
        try:
            return asyncio.run(self.generate_segment_async(
                pdf_path, segment_index, text, voice, speed
            ))
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None
    
    def generate_for_pdf(self, pdf_path: Path, segments: List[Dict],
                         voice: str = None, speed: float = None,
                         pregenerate: bool = False) -> Dict:
        """
        为整个PDF生成TTS
        
        Args:
            pdf_path: PDF文件路径
            segments: 分段列表，每个包含 'text' 和 'id'
            voice: 语音类型
            speed: 语速
            pregenerate: 是否预生成所有音频
        
        Returns:
            Dict: 分段索引到音频信息的映射
        """
        voice = voice or self.DEFAULT_VOICE
        speed = speed or self.DEFAULT_SPEED
        
        results = {}
        
        for segment in segments:
            seg_index = segment.get("id", 0)
            text = segment.get("text", "")
            
            if not text:
                continue
            
            # 检查缓存
            if self.is_segment_cached(pdf_path, seg_index, voice):
                info = self.get_segment_info(pdf_path, seg_index, voice)
                if info:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "audio_url": f"/api/reports/tts/audio_v2?pdf={hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]}&seg={seg_index}&voice={voice}",
                        "duration": info.get("duration", 0),
                        "ready": True,
                        "text_hash": info.get("text_hash", ""),
                    }
                    continue
            
            # 需要生成
            if pregenerate:
                info = self.generate_segment(pdf_path, seg_index, text, voice, speed)
                if info:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "audio_url": f"/api/reports/tts/audio_v2?pdf={hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]}&seg={seg_index}&voice={voice}",
                        "duration": info.get("duration", 0),
                        "ready": True,
                        "text_hash": info.get("text_hash", ""),
                    }
                else:
                    results[str(seg_index)] = {
                        "segment_index": seg_index,
                        "audio_url": f"/api/reports/tts/audio_v2?pdf={hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]}&seg={seg_index}&voice={voice}",
                        "duration": 0,
                        "ready": False,
                        "text_hash": hashlib.md5(text.encode()).hexdigest(),
                    }
            else:
                # 标记为未生成，按需生成
                results[str(seg_index)] = {
                    "segment_index": seg_index,
                    "audio_url": f"/api/reports/tts/audio_v2?pdf={hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]}&seg={seg_index}&voice={voice}",
                    "duration": 0,
                    "ready": False,
                    "text_hash": hashlib.md5(text.encode()).hexdigest(),
                }
        
        return results
    
    def clear_pdf_cache(self, pdf_path: Path) -> bool:
        """清理指定PDF的所有缓存"""
        try:
            pdf_dir = self._get_pdf_cache_dir(pdf_path)
            if pdf_dir.exists():
                shutil.rmtree(pdf_dir)
                logger.info(f"Cleared cache for {pdf_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache for {pdf_path}: {e}")
            return False
    
    def _estimate_duration(self, text: str, speed: float) -> float:
        """估算音频时长"""
        char_count = len(text)
        duration = char_count / 4 / speed
        return max(1.0, duration)


# 向后兼容 - 保持原有TTSService可用
from .tts_service import TTSService as TTSServiceLegacy
