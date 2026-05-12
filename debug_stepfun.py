#!/usr/bin/env python3
"""调试阶跃API返回"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.stepfun import StepfunClient, MODELS

print("=" * 60)
print("阶跃API调试测试")
print("=" * 60)

client = StepfunClient()
print(f"API Keys: {len(client.api_keys)}")
print(f"Base URL: {client.base_url}")
print(f"Model: {MODELS['deep']}")
print()

# 简化测试prompt
prompt = """请返回一个JSON对象，包含以下字段：
{
  "消息集合": [
    {
      "主领域": "环境生态",
      "子领域": "生物多样性",
      "关键事件": "测试事件",
      "简要描述": "这是一个测试",
      "利空利好": "中性",
      "消息大小": "中"
    }
  ]
}
只返回JSON，不要其他内容。"""

print("发送测试请求...")
print(f"Prompt长度: {len(prompt)}")

try:
    result = client.analyze(
        prompt=prompt,
        model=MODELS['deep'],
        max_tokens=2000,
        timeout=60,
        force_json=False  # 不强制JSON格式
    )
    
    if result:
        print(f"\n返回结果长度: {len(result)}")
        print(f"返回结果:\n{result[:500]}...")
        
        # 尝试解析JSON
        import json
        try:
            data = json.loads(result)
            print(f"\nJSON解析成功!")
            print(f"消息数量: {len(data.get('消息集合', []))}")
        except Exception as e:
            print(f"\nJSON解析失败: {e}")
    else:
        print("返回空结果")
        
except Exception as e:
    print(f"调用失败: {e}")
    import traceback
    traceback.print_exc()
