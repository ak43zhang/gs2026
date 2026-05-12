"""阶跃星辰 API 客户端 - 事件驱动分析专用（修复版）

修复内容:
1. 使用 step-3.5-flash-2603 Agent优化版模型
2. max_tokens 增加到 32000（阶跃最大值）
3. 添加 reasoning_effort 参数优化输出
4. 支持 256K 上下文
"""

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

STEP_BASE_URL = config_util.get_config('common.step_base_url') or 'https://api.stepfun.com/v1'

# 模型映射 - 使用Agent优化版
MODELS = {
    'fast': 'step-3.5-flash-2603',
    'standard': 'step-3.5-flash-2603',
    'deep': 'step-3.5-flash-2603',  # Agent优化版，支持256K上下文
}


class StepfunClient:
    """阶跃星辰API客户端"""
    
    def __init__(self):
        self.api_keys = STEP_API_KEYS
        self.base_url = STEP_BASE_URL
        self.key_index = 0
        
        if not self.api_keys:
            raise ValueError("未配置阶跃API Key")
        
        # 配置session（支持长连接和重试）
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        self.session.mount("https://", adapter)
        
        logger.info(f"StepfunClient 初始化: {len(self.api_keys)}个API Key")
    
    def _next_key(self) -> str:
        """轮询获取下一个API Key"""
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index += 1
        return key
    
    def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = MODELS['standard'],
        temperature: float = 0.3,
        max_tokens: int = 32000,  # 阶跃最大支持32000
        timeout: int = 300,
        force_json: bool = True,
        reasoning_effort: str = "high",  # Agent优化版参数
    ) -> Optional[str]:
        """
        调用阶跃API进行分析
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            model: 模型名称
            temperature: 采样温度
            max_tokens: 最大输出长度（最大32000）
            timeout: 请求超时秒数
            force_json: 是否强制JSON输出（通过prompt实现）
            reasoning_effort: 推理深度（low/high）
        
        Returns:
            AI回复文本，失败返回None
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
        
        # Agent优化版特有参数
        if model.endswith('-2603'):
            payload["reasoning_effort"] = reasoning_effort
        
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
                content = data['choices'][0]['message']['content']
                usage = data.get('usage', {})
                
                elapsed = time.time() - start
                logger.info(
                    f"阶跃API成功: model={model}, "
                    f"prompt={usage.get('prompt_tokens', 0)}, "
                    f"completion={usage.get('completion_tokens', 0)}, "
                    f"耗时={elapsed:.2f}s"
                )
                
                return content
                
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
                    logger.error(f"响应内容: {resp.text[:500]}")
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
        model=MODELS['deep'],  # step-3.5-flash-2603
        max_tokens=32000,      # 最大输出限制
        timeout=300,
        force_json=True,
        reasoning_effort="high"  # 设置为high提高推理质量
    )
