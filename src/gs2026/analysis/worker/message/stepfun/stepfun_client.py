"""阶跃星辰 API 客户端 - 事件驱动分析专用"""

import os
import time
import json
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gs2026.utils import config_util, log_util

logger = log_util.setup_logger("stepfun_client")

# ============ 配置 ============
STEP_API_KEYS = config_util.get_config('common.step_api_keys') or [
    os.getenv('STEP_API_KEY', '')
]
STEP_API_KEYS = [k for k in STEP_API_KEYS if k]

STEP_BASE_URL = config_util.get_config('common.step_base_url', 'https://api.stepfun.com/v1')

# 模型映射
MODELS = {
    'fast': 'step-1-8k',      # 快速分析
    'standard': 'step-1-32k',  # 标准分析（默认）
    'deep': 'step-1-128k',     # 深度分析
}


class StepfunClient:
    """阶跃API客户端（多Key轮询 + 自动重试）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.api_keys = STEP_API_KEYS
        self.base_url = STEP_BASE_URL
        self.key_index = 0
        
        if not self.api_keys:
            raise ValueError("STEP_API_KEYS 未配置，请检查 settings.yaml 或环境变量")
        
        # 创建带重试的Session
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, 
                     status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        
        logger.info(f"StepfunClient 初始化: {len(self.api_keys)}个API Key")
    
    def _next_key(self) -> str:
        """轮询获取下一个Key"""
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index += 1
        return key
    
    def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = MODELS['standard'],
        temperature: float = 0.3,
        max_tokens: int = 8000,
        timeout: int = 120,
        force_json: bool = True,
    ) -> Optional[str]:
        """
        调用阶跃API进行分析
        
        Args:
            prompt: 用户提示词（已构造好的完整Prompt）
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 采样温度（低温度保证稳定性）
            max_tokens: 最大输出长度
            timeout: 请求超时秒数
            force_json: 是否强制JSON输出
        
        Returns:
            AI回复文本（JSON格式），失败返回None
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "stream": False,
        }
        
        if force_json:
            payload["response_format"] = {"type": "json_object"}
        
        headers = {
            "Authorization": f"Bearer {self._next_key()}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(3):
            try:
                start = time.time()
                resp = self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
                resp.raise_for_status()
                data = resp.json()
                
                elapsed = time.time() - start
                usage = data.get("usage", {})
                logger.info(
                    f"阶跃API成功: model={model}, "
                    f"prompt={usage.get('prompt_tokens', 0)}, "
                    f"completion={usage.get('completion_tokens', 0)}, "
                    f"耗时={elapsed:.2f}s"
                )
                
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"].strip()
                
                logger.warning(f"阶跃API返回异常: {data}")
                return None
                
            except requests.exceptions.Timeout:
                logger.warning(f"阶跃API超时，重试 {attempt+1}/3")
                time.sleep(2 ** attempt)
            except requests.exceptions.HTTPError as e:
                if resp.status_code == 429:
                    logger.warning("阶跃API限流，切换Key重试...")
                    headers["Authorization"] = f"Bearer {self._next_key()}"
                    time.sleep(2)
                else:
                    logger.error(f"阶跃API HTTP错误: {e}")
                    time.sleep(1)
            except Exception as e:
                logger.error(f"阶跃API调用失败: {e}")
                time.sleep(1)
        
        return None


# 便捷函数（完全兼容 deepseek_analysis 接口）
def stepfun_analysis(prompt: str, _headless: bool = True) -> Optional[str]:
    """
    兼容层：直接替换 deepseek_analysis
    
    Args:
        prompt: 分析Prompt
        _headless: 兼容参数，阶跃版本忽略
    
    Returns:
        AI分析结果JSON字符串
    """
    from gs2026.analysis.worker.message.stepfun.prompts import SYSTEM_PROMPT_EVENT_DRIVEN
    
    client = StepfunClient()
    return client.analyze(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_EVENT_DRIVEN,
        model=MODELS['standard'],
        force_json=True
    )
