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
# 防护：如果配置为字符串而非列表，自动转为列表
if isinstance(VOLCENGINE_API_KEYS, str):
    VOLCENGINE_API_KEYS = [VOLCENGINE_API_KEYS]
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


# ============ LLM JSON修复工具 ============
import re
import json_repair as _json_repair


def repair_llm_json(text: str) -> str:
    """修复LLM输出的JSON格式问题

    使用json-repair库处理:
    1. 值缺少引号: "key": bare_value → "key": "bare_value"
    2. 未转义的内部引号: "key": "含"引号"的值" → 正确转义
    3. 尾部逗号: [1,2,3,] → [1,2,3]
    4. 截断JSON: 自动补全闭合括号
    """
    if not text:
        return text
    try:
        # json_repair.loads 直接返回Python对象（自动修复各类格式问题）
        obj = _json_repair.loads(text)
        # 转回标准JSON字符串
        import json as _json
        return _json.dumps(obj, ensure_ascii=False)
    except Exception:
        # 降级：使用正则修复基础问题
        text = re.sub(r',\s*([}\]])', r'\1', text)
        text = re.sub(r':\s*,', ': "",', text)
        text = text.replace('\uff1a"', ':"').replace('"\uff1a', '":')
        return text


def save_json_error(module_name: str, raw_json: str, error_msg: str) -> None:
    """将解析失败的JSON保存到MySQL用于后续分析优化

    表: analysis_json_errors (自动创建)
    """
    try:
        from sqlalchemy import create_engine, text as sql_text
        _url = config_util.get_config("common.url")
        _engine = create_engine(_url, pool_recycle=3600, pool_pre_ping=True)

        # 自动建表
        create_sql = """
        CREATE TABLE IF NOT EXISTS analysis_json_errors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            module_name VARCHAR(100),
            raw_json LONGTEXT,
            error_msg VARCHAR(500),
            json_length INT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        with _engine.connect() as conn:
            conn.execute(sql_text(create_sql))
            conn.commit()

        # 插入错误记录
        safe_json = raw_json.replace("'", "''") if raw_json else ''
        safe_err = str(error_msg).replace("'", "''")[:490]
        insert_sql = (
            f"INSERT INTO analysis_json_errors (module_name, raw_json, error_msg, json_length) "
            f"VALUES ('{module_name}', '{safe_json}', '{safe_err}', {len(raw_json) if raw_json else 0})"
        )
        with _engine.connect() as conn:
            conn.execute(sql_text(insert_sql))
            conn.commit()
        logger.info(f"[JSON错误] 已保存到analysis_json_errors: module={module_name}, len={len(raw_json) if raw_json else 0}")
    except Exception as e:
        logger.warning(f"[JSON错误] 保存失败: {e}")
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
        max_tokens=30000,
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
