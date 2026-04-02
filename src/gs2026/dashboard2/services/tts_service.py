"""
语音播报服务
使用 Edge TTS
"""
import asyncio
import edge_tts
from pathlib import Path
from typing import Dict
import aiofiles


class TTSService:
    """语音播报服务"""
    
    # 支持的音色
    VOICES = {
        'xiaoxiao': 'zh-CN-XiaoxiaoNeural',      # 晓晓 - 女声
        'xiaoyi': 'zh-CN-XiaoyiNeural',          # 晓伊 - 女声
        'yunjian': 'zh-CN-YunjianNeural',        # 云健 - 男声
        'yunxi': 'zh-CN-YunxiNeural',            # 云希 - 男声
        'yunyang': 'zh-CN-YunyangNeural',        # 云扬 - 男声
        'xiaochen': 'zh-CN-XiaochenNeural',      # 晓晨 - 女声
        'xiaohan': 'zh-CN-XiaohanNeural',        # 晓涵 - 女声
    }
    
    def __init__(self, cache_root: Path):
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
    
    async def generate(self, text: str, output_path: Path, 
                       voice: str = 'xiaoxiao', speed: float = 1.0) -> Dict:
        """
        生成语音文件
        
        Args:
            text: 要转换的文本
            output_path: 输出文件路径
            voice: 音色名称
            speed: 语速 (0.5-2.0)
        
        Returns:
            dict: {audio_path, duration, file_size}
        """
        # 获取音色ID
        voice_id = self.VOICES.get(voice, self.VOICES['xiaoxiao'])
        
        # 调整语速
        rate = f"{int((speed - 1) * 100)}%"
        
        # 创建通信对象
        communicate = edge_tts.Communicate(text, voice_id, rate=rate)
        
        # 生成音频
        await communicate.save(str(output_path))
        
        # 获取文件信息
        file_size = output_path.stat().st_size
        
        # 估算时长（粗略估计：中文约 4-5 字/秒）
        duration = len(text) // 4
        
        return {
            'audio_path': str(output_path),
            'duration': duration,
            'file_size': file_size
        }
    
    async def generate_for_report(self, report, output_dir: Path) -> Dict:
        """
        为报告生成语音
        
        Args:
            report: Report 对象
            output_dir: 输出目录
        
        Returns:
            dict: {audio_path, duration, file_size}
        """
        # 获取文本内容
        text = report.report_content_text or ''
        
        if not text:
            raise ValueError('报告没有文本内容')
        
        # 构建输出路径
        audio_filename = f"{Path(report.report_file_path).stem}.mp3"
        output_path = output_dir / audio_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 分段处理（如果文本过长）
        max_length = 5000  # 每段最大字符数
        if len(text) <= max_length:
            # 直接生成
            result = await self.generate(text, output_path)
        else:
            # 分段生成并合并
            result = await self._generate_in_segments(text, output_path, max_length)
        
        return result
    
    async def _generate_in_segments(self, text: str, output_path: Path, 
                                     max_length: int) -> Dict:
        """分段生成语音并合并"""
        # 按句子分割
        sentences = text.replace('。', '。|').replace('！', '！|').replace('？', '？|').split('|')
        
        segments = []
        current_segment = ''
        
        for sentence in sentences:
            if len(current_segment) + len(sentence) < max_length:
                current_segment += sentence
            else:
                if current_segment:
                    segments.append(current_segment)
                current_segment = sentence
        
        if current_segment:
            segments.append(current_segment)
        
        # 为每段生成临时音频文件
        temp_files = []
        total_duration = 0
        
        for i, segment in enumerate(segments):
            temp_path = output_path.parent / f"{output_path.stem}_part{i}.mp3"
            result = await self.generate(segment, temp_path)
            temp_files.append(temp_path)
            total_duration += result['duration']
        
        # 合并音频文件（使用简单的文件拼接）
        await self._merge_audio_files(temp_files, output_path)
        
        # 删除临时文件
        for temp_file in temp_files:
            temp_file.unlink(missing_ok=True)
        
        file_size = output_path.stat().st_size
        
        return {
            'audio_path': str(output_path),
            'duration': total_duration,
            'file_size': file_size
        }
    
    async def _merge_audio_files(self, input_files: list, output_file: Path):
        """合并多个 MP3 文件"""
        # 简单拼接 MP3 文件（MP3 格式允许直接拼接）
        async with aiofiles.open(output_file, 'wb') as outfile:
            for input_file in input_files:
                async with aiofiles.open(input_file, 'rb') as infile:
                    content = await infile.read()
                    await outfile.write(content)
    
    def get_cache_path(self, report_id: int, report_type: str, 
                       report_date: str, report_name: str) -> Path:
        """获取缓存路径"""
        # 按类型和日期组织目录
        cache_dir = self.cache_root / report_type / report_date[:4] / report_date[5:7]
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{Path(report_name).stem}.mp3"
        return cache_dir / filename
    
    def get_audio_url(self, cache_path: Path) -> str:
        """获取音频 URL"""
        # 相对于 output 目录的路径
        relative_path = cache_path.relative_to(self.cache_root.parent)
        return f"/output/{relative_path}"


# 同步包装器（方便在 Flask 中调用）
class SyncTTSService:
    """同步 TTS 服务包装器"""
    
    def __init__(self, cache_root: Path):
        self.async_service = TTSService(cache_root)
        self.loop = asyncio.new_event_loop()
    
    def generate(self, text: str, output_path: Path, 
                 voice: str = 'xiaoxiao', speed: float = 1.0) -> Dict:
        """同步生成语音"""
        return self.loop.run_until_complete(
            self.async_service.generate(text, output_path, voice, speed)
        )
    
    def generate_for_report(self, report, output_dir: Path) -> Dict:
        """同步为报告生成语音"""
        return self.loop.run_until_complete(
            self.async_service.generate_for_report(report, output_dir)
        )
