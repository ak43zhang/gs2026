"""火山方舟（Volcengine Ark）API 客户端 - 事件驱动分析专用

兼容OpenAI接口格式，支持：
- doubao-pro 系列模型 / 自定义 Endpoint
- API Key 轮询
- 自动重试与限流处理
"""

import os
import time
from typing import Optional, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gs2026.utils import config_util, log_util

logger = log_util.setup_logger("volcengine_client")

# ============ 配置 ============
VOLCENGINE_API_KEYS: List[str] = config_util.get_config('common.volcengine_api_keys') or [
    os.getenv('VOLCENGINE_API_KEY', '')
]
VOLCENGINE_API_KEYS = [k for k in VOLCENGINE_API_KEYS if k]

VOLCENGINE_BASE_URL: str = (
    config_util.get_config('common.volcengine_base_url')
    or 'https://ark.cn-beijing.volces.com/api/v3'
)

VOLCENGINE_MODEL: str = (
    config_util.get_config('common.volcengine_model')
    or 'doubao-pro-32k'
)


class VolcengineClient:
    """火山方舟API客户端（OpenAI兼容格式）"""

    def __init__(self):
        self.api_keys = VOLCENGINE_API_KEYS
        self.base_url = VOLCENGINE_BASE_URL
        self.default_model = VOLCENGINE_MODEL
        self.key_index = 0

        if not self.api_keys:
            raise ValueError("未配置火山方舟API Key（common.volcengine_api_keys）")

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

        logger.info(
            f"VolcengineClient 初始化: {len(self.api_keys)}个API Key, "
            f"model={self.default_model}, base_url={self.base_url}"
        )

    def _next_key(self) -> str:
        """轮询获取下一个API Key"""
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index += 1
        return key

    def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 300,
        force_json: bool = True,
    ) -> Optional[str]:
        """
        调用火山方舟API进行分析

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            model: 模型名称或Endpoint ID（默认使用配置值）
            temperature: 采样温度
            max_tokens: 最大输出长度
            timeout: 请求超时秒数
            force_json: 是否强制JSON输出（通过prompt引导）

        Returns:
            AI回复文本，失败返回None
        """
        use_model = model or self.default_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "stream": False,
        }

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
                    f"[火山方舟] API成功: model={use_model}, "
                    f"prompt_tokens={usage.get('prompt_tokens', 0)}, "
                    f"completion_tokens={usage.get('completion_tokens', 0)}, "
                    f"耗时={elapsed:.2f}s"
                )

                return content

            except requests.exceptions.Timeout:
                logger.warning(f"[火山方舟] API超时，重试 {attempt + 1}/3")
                time.sleep(2 ** attempt)
            except requests.exceptions.HTTPError:
                status = resp.status_code if resp else 0
                if status == 429:
                    logger.warning("[火山方舟] API限流，切换Key重试...")
                    headers["Authorization"] = f"Bearer {self._next_key()}"
                    time.sleep(2)
                else:
                    logger.error(f"[火山方舟] HTTP错误 {status}: {resp.text[:500]}")
                    time.sleep(1)
            except Exception as e:
                logger.error(f"[火山方舟] API调用失败: {e}")
                time.sleep(1)

        return None


# ============ 便捷函数（兼容 deepseek_analysis / stepfun_analysis 接口）============
def volcengine_analysis(prompt: str, _headless: bool = True) -> Optional[str]:
    """
    兼容层：直接替换 deepseek_analysis / stepfun_analysis

    Args:
        prompt: 分析Prompt（已包含完整指令，无需system_prompt）
        _headless: 兼容参数，火山方舟版本忽略

    Returns:
        AI分析结果JSON字符串
    """
    client = VolcengineClient()
    result = client.analyze(
        prompt=prompt,
        system_prompt="你是一位顶级金融分析师。只输出合法JSON，不要添加markdown标记、代码块或任何解释文字。",
        model=VOLCENGINE_MODEL,
        max_tokens=60000,
        timeout=600,
        force_json=True,
    )

    # 剥离markdown代码块包裹（API常见行为）
    if result:
        result = result.strip()
        if result.startswith('```'):
            # 去掉开头的 ```json 或 ```
            first_newline = result.find('\n')
            if first_newline != -1:
                result = result[first_newline + 1:]
            # 去掉结尾的 ```
            if result.endswith('```'):
                result = result[:-3].rstrip()

    return result
