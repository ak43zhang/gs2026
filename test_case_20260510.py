#!/usr/bin/env python3
"""测试用例: 2026-05-10 环境生态-生物多样性"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.stepfun import stepfun_ai

# 测试数据
query_list = [('2026-05-10', '环境生态', '生物多样性')]
bk_dic_str = '环保,新能源,碳中和,生态农业,水处理'
gn_dic_str = '碳中和,垃圾分类,污水处理,生态修复,绿色发展'
table_name = 'news_area'
analysis_table_name = 'analysis_area2026'

print("=" * 60)
print("测试用例: 2026-05-10 环境生态-生物多样性")
print("=" * 60)
print()

print("输入参数:")
print(f"  日期: 2026-05-10")
print(f"  主领域: 环境生态")
print(f"  子领域: 生物多样性")
print(f"  板块字典: {bk_dic_str}")
print(f"  概念字典: {gn_dic_str}")
print()

print("开始调用 stepfun_ai...")
print()

try:
    stepfun_ai(
        query_list=query_list,
        bk_dic_str=bk_dic_str,
        gn_dic_str=gn_dic_str,
        table_name=table_name,
        analysis_table_name=analysis_table_name,
        _headless=True
    )
    print()
    print("=" * 60)
    print("测试完成")
except Exception as e:
    print()
    print("=" * 60)
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
