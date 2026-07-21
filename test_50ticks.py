"""
快速验证脚本：只处理20260605前50个tick，打印扩展字段并写入临时表

使用方法:
    cd F:\pyworkspace2026\gs2026
    .venv\Scripts\python test_50ticks.py
"""
import sys
sys.path.insert(0, 'scripts')
sys.path.insert(0, r'src\gs2026\monitor')

# 强制清除缓存
for mod in list(sys.modules.keys()):
    if 'monitor_bond' in mod or 'compute_engine' in mod or 'field_registry' in mod:
        del sys.modules[mod]

import json
import pymysql
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from collections import defaultdict

# 导入计算引擎
try:
    from compute_engine import ComputeEngine, _unified_imported
    from field_registry import get_field_def
    print(f"[OK] 导入成功: _unified_imported = {_unified_imported}")
except ImportError as e:
    print(f"[ERROR] 导入失败: {e}")
    print(f"sys.path = {sys.path}")
    raise

print("=" * 70)
print("快速验证：20260605 前50个tick扩展字段计算与写入")
print("=" * 70)

# 配置
DB_URL = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8'
TABLE_NAME = 'monitor_zq_sssj_20260605'
TEMP_TABLE = 'test_50ticks_temp'
MAX_TICKS = 50

# 连接数据库
print(f"\n[1] 连接数据库并读取前{MAX_TICKS}个时间点")
engine = create_engine(DB_URL)

# 读取前50个时间点
sql = text(f"""SELECT DISTINCT `time` FROM {TABLE_NAME} 
WHERE `time` >= '09:30:00' ORDER BY `time` LIMIT {MAX_TICKS}""")
with engine.connect() as conn:
    times = [r[0] for r in conn.execute(sql).fetchall()]
print(f"    时间点数量: {len(times)}")
print(f"    时间范围: {times[0]} ~ {times[-1]}")

# 读取这些时间点的数据
print(f"\n[2] 读取数据")
placeholders = ', '.join([f":t_{j}" for j in range(len(times))])
data_sql = text(f"""SELECT `bond_code`, `time`, `price`, `change_pct`, `amount` 
FROM {TABLE_NAME} WHERE `time` IN ({placeholders}) 
ORDER BY `time`, `bond_code`""")
params = {f"t_{j}": t for j, t in enumerate(times)}
df = pd.read_sql(data_sql, engine, params=params)
print(f"    总行数: {len(df)}")
print(f"    债券数: {df['bond_code'].nunique()}")
print(f"    平均每tick行数: {len(df) // len(times)}")

# 初始化计算引擎
print(f"\n[3] 初始化ComputeEngine并处理数据")
cmpt = ComputeEngine()
fields_set = {'ext_indicators'}

# 处理每个tick并收集结果
all_results = []
sample_bond = df['bond_code'].iloc[0]  # 取第一个债券作为样本

print(f"\n[4] 逐tick处理 (样本债券: {sample_bond})")
print("-" * 70)

grouped = df.groupby('time', sort=True)
for i, (tick_time, df_tick) in enumerate(grouped):
    tick_time_str = str(tick_time).split()[-1] if ' ' in str(tick_time) else str(tick_time)
    
    # 处理tick
    tick_results = cmpt.process_tick(df_tick, tick_time_str, fields_set)
    
    # 收集样本债券的结果
    if 'ext_indicators' in tick_results and sample_bond in tick_results['ext_indicators']:
        ext_json = tick_results['ext_indicators'][sample_bond]
        if ext_json:
            ext_dict = json.loads(ext_json)
            slope_2m = ext_dict.get('weighted_slope_2m')
            slope_5m = ext_dict.get('weighted_slope_5m')
            slope_15m = ext_dict.get('weighted_slope_15m')
            status = "✅" if slope_2m is not None else "❌"
            print(f"tick {i:2d} ({tick_time_str}): slope_2m={slope_2m}, slope_5m={slope_5m}, slope_15m={slope_15m} {status}")
        else:
            print(f"tick {i:2d} ({tick_time_str}): ext_json=None")
    else:
        print(f"tick {i:2d} ({tick_time_str}): 无ext_indicators")
    
    # 收集所有结果用于写入临时表
    if 'ext_indicators' in tick_results:
        for code, ext_json in tick_results['ext_indicators'].items():
            all_results.append({
                'bond_code': code,
                'time': tick_time_str,
                'ext_indicators': ext_json
            })

print("-" * 70)
print(f"    共处理 {len(all_results)} 条记录")

# 创建临时表并写入
print(f"\n[5] 创建临时表 {TEMP_TABLE} 并写入数据")
conn = pymysql.connect(host='192.168.0.101', user='root', password='123456', 
                       database='gs', charset='utf8')
cur = conn.cursor()

# 删除旧临时表
cur.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE}")

# 创建临时表
cur.execute(f"""
CREATE TABLE {TEMP_TABLE} (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bond_code VARCHAR(20) NOT NULL,
    time VARCHAR(10) NOT NULL,
    ext_indicators TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_code_time (bond_code, time)
)
""")

# 批量写入
batch_size = 1000
for i in range(0, len(all_results), batch_size):
    batch = all_results[i:i+batch_size]
    values = [(r['bond_code'], r['time'], r['ext_indicators']) for r in batch]
    cur.executemany(
        f"INSERT INTO {TEMP_TABLE} (bond_code, time, ext_indicators) VALUES (%s, %s, %s)",
        values
    )
conn.commit()

# 验证写入
print(f"    写入完成，验证数据...")
cur.execute(f"SELECT COUNT(*) FROM {TEMP_TABLE}")
count = cur.fetchone()[0]
print(f"    临时表行数: {count}")

# 抽样检查
cur.execute(f"""
    SELECT bond_code, time, ext_indicators FROM {TEMP_TABLE} 
    WHERE bond_code = %s ORDER BY time LIMIT 10
""", (sample_bond,))
rows = cur.fetchall()
print(f"\n[6] 样本债券 {sample_bond} 的前10条记录:")
print("-" * 70)
for row in rows:
    ext = json.loads(row[2]) if row[2] else {}
    s2 = ext.get('weighted_slope_2m')
    s5 = ext.get('weighted_slope_5m')
    s15 = ext.get('weighted_slope_15m')
    status = "✅" if s2 is not None else "❌"
    print(f"  {row[0]} @ {row[1]}: slope_2m={s2}, slope_5m={s5}, slope_15m={s15} {status}")

# 统计有值/无值
cur.execute(f"""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN ext_indicators LIKE '%\"weighted_slope_2m\": null%' THEN 1 ELSE 0 END) as null_count,
        SUM(CASE WHEN ext_indicators LIKE '%\"weighted_slope_2m\":%' AND ext_indicators NOT LIKE '%\"weighted_slope_2m\": null%' THEN 1 ELSE 0 END) as value_count
    FROM {TEMP_TABLE}
""")
stats = cur.fetchone()
print(f"\n[7] 统计结果:")
print(f"    总记录数: {stats[0]}")
print(f"    slope_2m为null: {stats[1]} ({stats[1]/stats[0]*100:.1f}%)")
print(f"    slope_2m有值: {stats[2]} ({stats[2]/stats[0]*100:.1f}%)")

# 清理（可选：保留临时表供检查）
# cur.execute(f"DROP TABLE {TEMP_TABLE}")
# conn.commit()
# print(f"\n[8] 临时表已删除")

conn.close()
engine.dispose()

print("\n" + "=" * 70)
print("验证完成！")
print(f"临时表 {TEMP_TABLE} 保留在数据库中，可用以下SQL检查:")
print(f"  SELECT * FROM {TEMP_TABLE} WHERE bond_code = '{sample_bond}' LIMIT 10;")
print("=" * 70)
