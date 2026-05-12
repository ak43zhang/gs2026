#!/usr/bin/env python3
"""阶跃星辰API测试脚本"""

import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

print('=== Test 1: Client Initialization ===')
try:
    from gs2026.analysis.worker.message.stepfun import StepfunClient
    client = StepfunClient()
    print('[OK] Client initialized successfully')
    print(f'    API Keys count: {len(client.api_keys)}')
    print(f'    Base URL: {client.base_url}')
except Exception as e:
    print(f'[FAIL] Client initialization failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print('=== Test 2: Simple API Call ===')
try:
    result = client.analyze(
        prompt='Please return JSON: {"test": "ok", "timestamp": "2026-05-12"}',
        system_prompt='You are a test assistant, return only JSON format',
        model='step-1-8k',
        max_tokens=500,
        timeout=60
    )
    if result:
        print('[OK] API call successful')
        print(f'    Result: {result[:200]}')
        # Verify JSON
        try:
            data = json.loads(result)
            print(f'    JSON parse: OK')
            print(f'    Content: {data}')
        except:
            print(f'    JSON parse: FAIL (not standard JSON)')
    else:
        print('[FAIL] API returned empty result')
except Exception as e:
    print(f'[FAIL] API call failed: {e}')
    import traceback
    traceback.print_exc()

print()
print('=== Test 3: Prompt Templates ===')
try:
    from gs2026.analysis.worker.message.stepfun.prompts import (
        SYSTEM_PROMPT_EVENT_DRIVEN,
        EVENT_DRIVEN_PROMPT_TEMPLATE
    )
    print('[OK] Prompt templates loaded')
    print(f'    System prompt length: {len(SYSTEM_PROMPT_EVENT_DRIVEN)} chars')
    print(f'    Template length: {len(EVENT_DRIVEN_PROMPT_TEMPLATE)} chars')
except Exception as e:
    print(f'[FAIL] Prompt templates load failed: {e}')

print()
print('=== Test 4: Simulated Event Analysis ===')
try:
    prompt = EVENT_DRIVEN_PROMPT_TEMPLATE.format(
        main_area='科技',
        child_area='AI',
        bk_dic_str='半导体,人工智能,计算机',
        gn_dic_str='ChatGPT,大模型,AIGC',
        query='2026-05-12全球重要事件：OpenAI发布GPT-5，性能提升10倍'
    )
    print(f'[OK] Prompt constructed, length: {len(prompt)} chars')
    
    # Actual API call (using 8k model for quick test)
    print('    Calling Stepfun API...')
    result = client.analyze(
        prompt=prompt[:2000],  # Truncate for test
        system_prompt=SYSTEM_PROMPT_EVENT_DRIVEN,
        model='step-1-8k',
        max_tokens=2000,
        timeout=90
    )
    if result:
        print('[OK] API call successful')
        print(f'    Response length: {len(result)} chars')
        print(f'    First 500 chars: {result[:500]}')
    else:
        print('[FAIL] API returned empty result')
except Exception as e:
    print(f'[FAIL] Simulated analysis failed: {e}')
    import traceback
    traceback.print_exc()

print()
print('=== Test Complete ===')
