"""验证4项修复"""
with open(r'G:\report\智能报告\智能日报_2026-06-05.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 字数和阅读时间
import re
idx = content.find('全文约')
if idx > 0:
    print('✅ 1. 字数/阅读时间:', content[idx:idx+30])
else:
    print('❌ 1. 未找到字数信息')

# 2. 涨停分析
if '涨停分析' in content and '涨停有预期' not in content:
    print('✅ 2. 已改为"涨停分析"')
else:
    print('❌ 2. 文案未修改')

# 3. 连板显示
if '首板' in content:
    print('✅ 3. continuity=1显示为"首板"')
else:
    print('❌ 3. 未找到"首板"')

# 4. 概念热度
if '概念热度' in content:
    idx = content.find('概念热度')
    print('✅ 4. 概念热度:', content[idx:idx+100])
else:
    print('❌ 4. 未找到概念热度')
