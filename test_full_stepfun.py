#!/usr/bin/env python3
"""调试阶跃API返回 - 完整测试"""

import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.stepfun import StepfunClient, MODELS
from gs2026.analysis.worker.message.stepfun.prompts import (
    SYSTEM_PROMPT_EVENT_DRIVEN,
    EVENT_DRIVEN_PROMPT_TEMPLATE
)

print("=" * 60)
print("阶跃API完整测试 - 2026-05-10 环境生态-生物多样性")
print("=" * 60)

client = StepfunClient()

# 构造完整Prompt
main_area = '环境生态'
child_area = '生物多样性'
bk_dic_str = '环保,新能源,碳中和,生态农业,水处理'
gn_dic_str = '碳中和,垃圾分类,污水处理,生态修复,绿色发展'
query = '2026-05-10全球重要事件'

prompt = EVENT_DRIVEN_PROMPT_TEMPLATE
prompt = prompt.replace('__MAIN_AREA__', main_area)
prompt = prompt.replace('__CHILD_AREA__', child_area)
prompt = prompt.replace('__BK_DIC_STR__', bk_dic_str)
prompt = prompt.replace('__GN_DIC_STR__', gn_dic_str)
prompt = prompt.replace('__QUERY__', query)

print(f"Prompt长度: {len(prompt)} 字符")
print(f"模型: {MODELS['deep']}")
print()

print("发送请求...")
try:
    result = client.analyze(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_EVENT_DRIVEN,
        model=MODELS['deep'],
        max_tokens=16000,
        timeout=300,
        force_json=False
    )
    
    if result:
        print(f"返回长度: {len(result)} 字符")
        
        # 保存完整结果到文件
        with open(r'F:\pyworkspace2026\gs2026\stepfun_result.json', 'w', encoding='utf-8') as f:
            f.write(result)
        print("结果已保存到: stepfun_result.json")
        
        # 解析JSON
        try:
            data = json.loads(result)
            messages = data.get('消息集合', [])
            print(f"消息数量: {len(messages)}")
            
            if messages:
                print("\n第一条消息:")
                msg = messages[0]
                for key in ['主领域', '子领域', '关键事件', '利空利好', '消息大小']:
                    print(f"  {key}: {msg.get(key, 'N/A')}")
            
            print("\n[OK] 测试成功!")
        except Exception as e:
            print(f"\n[FAIL] JSON解析失败: {e}")
            print(f"返回内容前500字符:\n{result[:500]}")
    else:
        print("[FAIL] 返回空结果")
        
except Exception as e:
    print(f"[FAIL] 调用失败: {e}")
    import traceback
    traceback.print_exc()
