"""
手动触发一次潜在标的挖掘（测试用）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.analysis.worker.realtime.anomaly_potential import find_potential_stocks

print("=" * 50)
print("手动触发潜在标的挖掘")
print("=" * 50)

# 执行挖掘（会调用AI，需要等待）
result = find_potential_stocks('2026-06-24', trigger_type='manual')

print(f"\n挖掘完成，返回 {len(result)} 只潜在标的：")
for item in result:
    print(f"  #{item['rank']} {item['code']} {item['name']}: {item['total_score']}分")
    print(f"    涉及主线: {item['mainline_count']}条")
    print(f"    介入点: {item['suggested_entry']}")
    print(f"    风险: {item['risk_level']}")
    print()
