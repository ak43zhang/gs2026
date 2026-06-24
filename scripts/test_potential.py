"""
测试潜在标的挖掘功能
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.analysis.worker.realtime.anomaly_potential import (
    find_potential_stocks, 
    get_potential_by_time,
    get_potential_history
)

# 测试获取历史
print("=" * 50)
print("测试：获取潜在标的历史")
print("=" * 50)
history = get_potential_history('2026-06-24')
print(f"历史记录数: {len(history)}")
for h in history[:5]:
    print(f"  {h['time']} ({h['type']}): {h['count']}只")

# 测试获取最新
print("\n" + "=" * 50)
print("测试：获取最新潜在标的")
print("=" * 50)
potential = get_potential_by_time('2026-06-24', None)
print(f"潜在标的数: {len(potential)}")
for p in potential[:3]:
    print(f"  #{p['rank_num']} {p['stock_code']} {p['stock_name']}: {p['total_score']}分")

# 测试手动挖掘（谨慎使用，会调用AI）
# print("\n" + "=" * 50)
# print("测试：手动挖掘潜在标的")
# print("=" * 50)
# result = find_potential_stocks('2026-06-24', trigger_type='manual')
# print(f"挖掘结果: {len(result)}只")

print("\n测试完成")
