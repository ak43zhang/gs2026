"""
排查API返回的window_count
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService

ds = DataService()

# 测试 get_ranking_at_time API
print("=== 测试 get_ranking_at_time ===")
result = ds.get_ranking_at_time('bond', limit=10, date='20260618', time_str='14:43:24')
print(f"返回条数: {len(result)}")
if result:
    import pandas as pd
    df = pd.DataFrame(result)
    print("\n返回字段:", list(df.columns))
    if 'window_count' in df.columns:
        print("\nwindow_count 值:")
        print(df[['code', 'name', 'window_count']].head(10).to_string(index=False))
    else:
        print("\n没有 window_count 字段!")
