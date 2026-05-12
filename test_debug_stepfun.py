#!/usr/bin/env python3
"""调试阶跃API返回 - 简化测试"""

import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.stepfun import StepfunClient, MODELS

print("=" * 60)
print("阶跃API调试测试")
print("=" * 60)

client = StepfunClient()

# 简化Prompt - 只要求返回5条消息
prompt = """分析2026-05-10环境生态领域生物多样性的重要事件。

请返回JSON格式：
{
  "消息集合": [
    {
      "主领域": "环境生态",
      "子领域": "生物多样性",
      "时间": "2026-05-10 09:00:00",
      "事件来源": "新华社",
      "关键事件": "事件标题",
      "简要描述": "一句话描述",
      "利空利好": "利好",
      "消息大小": "大",
      "涉及板块": "环保,新能源",
      "涉及概念": "碳中和,绿色发展",
      "股票代码": "000001,000002",
      "原因分析": "原因",
      "重要程度评分": "10",
      "业务影响维度评分": "30",
      "综合评分": "70",
      "深度分析": ["成本控制:原因+5分"]
    }
  ]
}

只返回5条最重要的消息，确保JSON格式完整可解析。"""

print(f"Prompt长度: {len(prompt)} 字符")
print(f"模型: {MODELS['deep']}")
print()

print("发送请求...")
try:
    result = client.analyze(
        prompt=prompt,
        model=MODELS['deep'],
        max_tokens=4000,
        timeout=120,
        force_json=False
    )
    
    print(f"返回结果类型: {type(result)}")
    print(f"返回结果长度: {len(result) if result else 0} 字符")
    
    if result:
        # 保存到文件
        with open(r'F:\pyworkspace2026\gs2026\stepfun_debug.json', 'w', encoding='utf-8') as f:
            f.write(result)
        print("结果已保存到: stepfun_debug.json")
        
        # 显示前1000字符
        print(f"\n返回内容前1000字符:\n{result[:1000]}")
        
        # 尝试解析
        try:
            data = json.loads(result)
            messages = data.get('消息集合', [])
            print(f"\n[OK] JSON解析成功!")
            print(f"消息数量: {len(messages)}")
        except Exception as e:
            print(f"\n[FAIL] JSON解析失败: {e}")
    else:
        print("[FAIL] 返回空结果")
        
except Exception as e:
    print(f"[FAIL] 调用失败: {e}")
    import traceback
    traceback.print_exc()
