import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

date = '20260731'
time_str = '09:40:03'
code = '123118'

# 模拟 _get_ranking_fast 的逻辑
print("=== 步骤1: _get_ranking_fast ===")
table = f"monitor_zq_top30_{date}"
sql = f"""
    SELECT code, name, COUNT(*) as cnt FROM {table}
    WHERE time <= '{time_str}' GROUP BY code, name
"""
with engine.connect() as conn:
    rows = conn.execute(text(sql)).fetchall()
    counters = {r[0]: {'name': r[1], 'count': r[2]} for r in rows}
    
# 找到123118的count
if code in counters:
    print(f"123118的count（累计次数）: {counters[code]['count']}")
else:
    print(f"123118不在结果中")

# 模拟 _get_bond_window_count_batch 的逻辑
print("\n=== 步骤2: _get_bond_window_count_batch ===")
hh = time_str[:2]
mm = int(time_str[3:5])
window_start = f"{hh}:{(mm//10)*10:02d}:00"
print(f"window_start: {window_start}")

sql2 = f"""
    SELECT t1.code, t1.window_count
    FROM {table} t1
    INNER JOIN (
        SELECT code, MAX(time) as max_time
        FROM {table}
        WHERE code = '{code}' 
          AND time >= '{window_start}'
          AND time <= '{time_str}'
        GROUP BY code
    ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
"""
with engine.connect() as conn:
    result = conn.execute(text(sql2)).fetchall()
    if result:
        print(f"123118的window_count: {result[0][1]}")
    else:
        print(f"123118在区间{window_start}-{time_str}无记录")

print("\n=== 结论 ===")
print(f"count（累计）: {counters.get(code, {}).get('count', 'N/A')}")
print(f"window_count（区间）: {result[0][1] if result else 0}")
