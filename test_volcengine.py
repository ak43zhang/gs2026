"""测试火山方舟API返回内容"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import VolcengineClient

client = VolcengineClient()
result = client.analyze(
    prompt='请用JSON格式返回：{"test": "hello", "status": "ok"}',
    system_prompt='你是一个JSON生成器，只输出合法JSON，不加任何解释。',
    max_tokens=200,
    timeout=30
)

print('=' * 60)
print('RAW RESPONSE (repr):')
print('=' * 60)
print(repr(result))
print('=' * 60)
print('CONTENT:')
print('=' * 60)
print(result)
