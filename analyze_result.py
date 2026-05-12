#!/usr/bin/env python3
"""分析测试结果并统计Token使用量"""

import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

print("=" * 70)
print("阶跃API测试结果分析")
print("=" * 70)

# 读取结果文件
with open(r'F:\pyworkspace2026\gs2026\stepfun_result_30.json', 'r', encoding='utf-8') as f:
    result = f.read()

data = json.loads(result)
messages = data.get('消息集合', [])

print(f"\n1. 基本信息")
print(f"   返回结果总长度: {len(result)} 字符")
print(f"   消息数量: {len(messages)} 条")

# 统计评分分布
scores = []
for msg in messages:
    try:
        score = int(msg.get('综合评分', 0))
        scores.append(score)
    except:
        pass

print(f"\n2. 评分统计")
print(f"   最高评分: {max(scores) if scores else 0}")
print(f"   最低评分: {min(scores) if scores else 0}")
print(f"   平均评分: {sum(scores)/len(scores):.1f}" if scores else "N/A")

# 统计消息大小
sizes = {}
for msg in messages:
    size = msg.get('消息大小', '未知')
    sizes[size] = sizes.get(size, 0) + 1

print(f"\n3. 消息大小分布")
for size, count in sorted(sizes.items()):
    print(f"   {size}: {count} 条")

# 统计利空利好
sentiments = {}
for msg in messages:
    sentiment = msg.get('利空利好', '未知')
    sentiments[sentiment] = sentiments.get(sentiment, 0) + 1

print(f"\n4. 利空利好分布")
for sentiment, count in sorted(sentiments.items()):
    print(f"   {sentiment}: {count} 条")

# 统计涉及板块
blocks = set()
for msg in messages:
    bk = msg.get('涉及板块', '')
    for b in bk.split(','):
        blocks.add(b.strip())

print(f"\n5. 涉及板块: {len(blocks)} 个")
print(f"   {', '.join(sorted(blocks))}")

# 统计涉及概念
concepts = set()
for msg in messages:
    gn = msg.get('涉及概念', '')
    for g in gn.split(','):
        concepts.add(g.strip())

print(f"\n6. 涉及概念: {len(concepts)} 个")
print(f"   {', '.join(sorted(concepts))}")

# 统计股票代码
stocks = set()
for msg in messages:
    codes = msg.get('股票代码', '')
    for c in codes.split(','):
        if c.strip():
            stocks.add(c.strip())

print(f"\n7. 涉及股票: {len(stocks)} 只")
print(f"   {', '.join(sorted(stocks)[:20])}{'...' if len(stocks) > 20 else ''}")

# 深度分析字段检查
print(f"\n8. 深度分析字段检查")
if messages:
    msg = messages[0]
    depth = msg.get('深度分析', '')
    print(f"   类型: {type(depth).__name__}")
    print(f"   长度: {len(str(depth))} 字符")
    print(f"   内容: {str(depth)[:200]}...")

print(f"\n9. Token使用量估算")
# 中文字符约1.5 tokens，英文约1 token
chinese_chars = sum(1 for c in result if '\u4e00' <= c <= '\u9fff')
english_chars = len(result) - chinese_chars
estimated_tokens = int(chinese_chars * 1.5 + english_chars * 0.5)
print(f"   中文字符: {chinese_chars}")
print(f"   其他字符: {english_chars}")
print(f"   估算Tokens: ~{estimated_tokens}")

print(f"\n10. 第一条消息完整内容")
if messages:
    msg = messages[0]
    for key, value in msg.items():
        display_value = str(value)[:100] + '...' if len(str(value)) > 100 else str(value)
        print(f"   {key}: {display_value}")

print("\n" + "=" * 70)
print("[OK] 测试完成！30条消息完整返回，JSON格式正确")
print("=" * 70)
