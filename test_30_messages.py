#!/usr/bin/env python3
"""完整测试 - 30条消息 + Token使用量统计"""

import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.stepfun import StepfunClient, MODELS
from gs2026.analysis.worker.message.stepfun.prompts import (
    SYSTEM_PROMPT_EVENT_DRIVEN,
    EVENT_DRIVEN_PROMPT_TEMPLATE
)

print("=" * 70)
print("阶跃API完整测试 - 2026-05-10 环境生态-生物多样性")
print("模型: step-3.5-flash-2603 (reasoning_effort=high)")
print("max_tokens: 32000")
print("=" * 70)

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

print(f"\nPrompt长度: {len(prompt)} 字符")
print(f"模型: {MODELS['deep']}")
print(f"reasoning_effort: high")
print(f"max_tokens: 32000")
print()

print("发送请求...")
print("预计需要2-3分钟，请等待...")
print()

try:
    result = client.analyze(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_EVENT_DRIVEN,
        model=MODELS['deep'],
        max_tokens=32000,
        timeout=300,
        force_json=False,
        reasoning_effort="high"
    )
    
    if result:
        print(f"返回结果长度: {len(result)} 字符")
        
        # 保存完整结果
        with open(r'F:\pyworkspace2026\gs2026\stepfun_result_30.json', 'w', encoding='utf-8') as f:
            f.write(result)
        print("结果已保存到: stepfun_result_30.json")
        
        # 解析JSON
        try:
            data = json.loads(result)
            messages = data.get('消息集合', [])
            
            print("\n" + "=" * 70)
            print("测试结果")
            print("=" * 70)
            print(f"消息数量: {len(messages)} 条")
            
            if messages:
                print("\n第一条消息示例:")
                msg = messages[0]
                for key in ['主领域', '子领域', '关键事件', '利空利好', '消息大小', '综合评分']:
                    print(f"  {key}: {msg.get(key, 'N/A')}")
                
                # 检查深度分析字段
                depth = msg.get('深度分析', [])
                print(f"  深度分析: {len(depth)} 个维度")
            
            print("\n[OK] JSON解析成功!")
            print(f"完整结果已保存，请查看文件获取详细信息")
            
        except Exception as e:
            print(f"\n[FAIL] JSON解析失败: {e}")
            print(f"返回内容前1000字符:\n{result[:1000]}")
            
            # 尝试找到JSON结束位置
            last_brace = result.rfind('}')
            if last_brace > 0:
                print(f"\n最后一个}}位置: {last_brace}")
                print(f"结果可能被截断，建议减少消息数量或精简字段")
    else:
        print("[FAIL] 返回空结果")
        
except Exception as e:
    print(f"[FAIL] 调用失败: {e}")
    import traceback
    traceback.print_exc()
