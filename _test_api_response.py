"""
测试债券API返回的数据结构
模拟 get_bond_ranking 的完整流程
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from datetime import datetime
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

date = '20260731'
time_str = '09:40:03'
code = '123118'

print("=== 模拟 get_bond_ranking ===\n")

# 步骤1: _get_ranking_fast
print("步骤1: _get_ranking_fast")
table = f"monitor_zq_top30_{date}"
sql = f"""
    SELECT code, name, COUNT(*) as cnt FROM {table}
    WHERE time <= '{time_str}' GROUP BY code, name
"""
with engine.connect() as conn:
    rows = conn.execute(text(sql)).fetchall()
    counters = {r[0]: {'name': r[1], 'count': r[2]} for r in rows}

# 找到123118
if code in counters:
    print(f"  123118: count={counters[code]['count']}")
    
# 构建data（模拟_get_ranking_fast返回）
data = [{'code': code, 'name': counters[code]['name'], 'count': counters[code]['count'], 'rank': 1}]
print(f"  data[0] after _get_ranking_fast: {data[0]}")

# 步骤2: _enrich_bond_data
print("\n步骤2: _enrich_bond_data")

# 模拟 _get_bond_window_count_batch
hh = time_str[:2]
mm = int(time_str[3:5])
window_start = f"{hh}:{(mm//10)*10:02d}:00"

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
    window_count_map = {row[0]: row[1] for row in result}

print(f"  window_count_map: {window_count_map}")

# 填充window_count
data[0]['window_count'] = window_count_map.get(code, 0)
print(f"  data[0] after _enrich_bond_data: {data[0]}")

print("\n=== 最终返回给前端的数据 ===")
print(f"code: {data[0]['code']}")
print(f"count: {data[0]['count']}")
print(f"window_count: {data[0]['window_count']}")

print("\n=== 结论 ===")
print(f"后端返回: count={data[0]['count']}, window_count={data[0]['window_count']}")
print(f"前端应该显示: 区间次数={data[0]['window_count']}")
if data[0]['window_count'] == 1:
    print("✅ 后端数据正确！")
else:
    print("❌ 后端数据错误！")
