#!/usr/bin/env python3
"""测试新Prompt - 验证深度分析数组格式"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
from gs2026.analysis.worker.message.stepfun import StepfunClient, MODELS
from gs2026.analysis.worker.message.stepfun.prompts import (
    SYSTEM_PROMPT_EVENT_DRIVEN,
    EVENT_DRIVEN_PROMPT_TEMPLATE
)

print("=" * 70)
print("测试新Prompt - 深度分析数组格式")
print("=" * 70)

client = StepfunClient()

# 构造Prompt
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
print(f"reasoning_effort: high")
print()

print("发送请求...")
print("预计需要2-3分钟...")
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
        print(f"返回长度: {len(result)} 字符")
        
        # 保存结果
        with open(r'F:\pyworkspace2026\gs2026\stepfun_result_array.json', 'w', encoding='utf-8') as f:
            f.write(result)
        print("结果已保存: stepfun_result_array.json")
        
        # 解析JSON
        try:
            data = json.loads(result)
            messages = data.get('消息集合', [])
            print(f"\n消息数量: {len(messages)}")
            
            if messages:
                msg = messages[0]
                print("\n第一条消息:")
                print(f"  主领域: {msg.get('主领域')}")
                print(f"  子领域: {msg.get('子领域')}")
                print(f"  关键事件: {msg.get('关键事件')}")
                
                # 检查深度分析字段
                depth = msg.get('深度分析', [])
                print(f"\n  深度分析类型: {type(depth).__name__}")
                print(f"  深度分析长度: {len(depth)}")
                
                if isinstance(depth, list):
                    print("  [OK] 深度分析是数组格式!")
                    print(f"\n  深度分析内容:")
                    for i, item in enumerate(depth[:5], 1):
                        print(f"    {i}. {item}")
                    if len(depth) > 5:
                        print(f"    ... 共{len(depth)}个维度")
                else:
                    print(f"  [FAIL] 深度分析不是数组!")
                    print(f"  实际值: {str(depth)[:200]}...")
            
            print("\n" + "=" * 70)
            print("[OK] JSON解析成功!")
            
        except Exception as e:
            print(f"\n[FAIL] JSON解析失败: {e}")
    else:
        print("[FAIL] 返回空结果")
        
except Exception as e:
    print(f"[FAIL] 调用失败: {e}")
    import traceback
    traceback.print_exc()
