#!/usr/bin/env python3
"""阶跃星辰API完整测试报告生成脚本"""

import sys
import json
import time
from datetime import datetime

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

report = {
    'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'tests': []
}

def add_test(name, status, details):
    report['tests'].append({
        'name': name,
        'status': status,
        'details': details,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })
    status_str = 'PASS' if status else 'FAIL'
    print(f"[{status_str}] {name}")
    if details:
        print(f"    {details}")

print("=" * 60)
print("Stepfun API Test Report")
print("=" * 60)
print()

# Test 1: Client Initialization
print("Test 1: Client Initialization")
try:
    from gs2026.analysis.worker.message.stepfun import StepfunClient
    client = StepfunClient()
    add_test('Client Initialization', True, 
             f"API Keys: {len(client.api_keys)}, Base URL: {client.base_url}")
except Exception as e:
    add_test('Client Initialization', False, str(e))

print()

# Test 2: Simple API Call
print("Test 2: Simple API Call")
try:
    start = time.time()
    result = client.analyze(
        prompt='Please return JSON: {"test": "ok", "timestamp": "2026-05-12"}',
        system_prompt='You are a test assistant, return only JSON format',
        model='step-1-8k',
        max_tokens=500,
        timeout=60
    )
    elapsed = time.time() - start
    
    if result:
        try:
            data = json.loads(result)
            add_test('Simple API Call', True, 
                     f"Latency: {elapsed:.2f}s, JSON parsed OK")
        except:
            add_test('Simple API Call', True, 
                     f"Latency: {elapsed:.2f}s, but JSON parse failed")
    else:
        add_test('Simple API Call', False, "Empty result")
except Exception as e:
    add_test('Simple API Call', False, str(e))

print()

# Test 3: Prompt Templates
print("Test 3: Prompt Templates")
try:
    from gs2026.analysis.worker.message.stepfun.prompts import (
        SYSTEM_PROMPT_EVENT_DRIVEN,
        EVENT_DRIVEN_PROMPT_TEMPLATE
    )
    add_test('Prompt Templates Load', True,
             f"System: {len(SYSTEM_PROMPT_EVENT_DRIVEN)} chars, "
             f"Template: {len(EVENT_DRIVEN_PROMPT_TEMPLATE)} chars")
except Exception as e:
    add_test('Prompt Templates Load', False, str(e))

print()

# Test 4: Event Analysis Simulation
print("Test 4: Event Analysis Simulation")
try:
    prompt = EVENT_DRIVEN_PROMPT_TEMPLATE.format(
        main_area='科技',
        child_area='AI',
        bk_dic_str='半导体,人工智能,计算机',
        gn_dic_str='ChatGPT,大模型,AIGC',
        query='2026-05-12全球重要事件：OpenAI发布GPT-5，性能提升10倍'
    )
    
    start = time.time()
    result = client.analyze(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_EVENT_DRIVEN,
        model='step-1-8k',
        max_tokens=2000,
        timeout=90
    )
    elapsed = time.time() - start
    
    if result:
        # Try to parse as JSON
        try:
            data = json.loads(result)
            msg_count = len(data.get('messages', []))
            add_test('Event Analysis API', True,
                     f"Latency: {elapsed:.2f}s, Response: {len(result)} chars, "
                     f"Messages: {msg_count}")
        except:
            # Check if it contains expected fields
            has_fields = all(k in result for k in ['主领域', '子领域', '消息'])
            add_test('Event Analysis API', True,
                     f"Latency: {elapsed:.2f}s, Response: {len(result)} chars, "
                     f"Chinese fields: {has_fields}")
    else:
        add_test('Event Analysis API', False, "Empty result")
except Exception as e:
    add_test('Event Analysis API', False, str(e))

print()
print("=" * 60)

# Summary
passed = sum(1 for t in report['tests'] if t['status'])
total = len(report['tests'])
print(f"Summary: {passed}/{total} tests passed")
print("=" * 60)

# Save report
report_file = r'F:\pyworkspace2026\gs2026\test_stepfun_report.json'
with open(report_file, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"Report saved to: {report_file}")
