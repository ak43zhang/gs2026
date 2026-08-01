import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')
from gs2026.dashboard.services.data_service import DataService

ds = DataService()
# 历史日期，走MySQL路径
data = ds.get_industry_ranking(limit=5, date='20260731', use_mysql=True)
print("返回条数:", len(data))
if data:
    print("第一条所有字段:")
    for k, v in data[0].items():
        print(f"  {k} = {v}")
    # 检查7个目标字段
    need = ['count','avg_change_pct','industry_cumulative_main_net','final_score','delta_change_pct','total','smooth_ratio']
    print("\n字段检查:")
    for k in need:
        status = 'OK' if k in data[0] else 'MISSING'
        print(f"  {k}: {status} (值={data[0].get(k)})")
