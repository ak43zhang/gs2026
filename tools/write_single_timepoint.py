"""写入单个时间点行业数据到MySQL和Redis（用于前端验证）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.disable(logging.WARNING)

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util, redis_util
from gs2026.monitor.monitor_stock import calculate_industry_topn

db_config = config_util.get_config('mysql', 'url')
if isinstance(db_config, dict):
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    url = db_config
engine = create_engine(url)

DATE_STR = '20260526'
TIME_STR = '10:00:00'
HY_TABLE = f'monitor_hy_top30_{DATE_STR}'
TOP30_TABLE = f'monitor_gp_top30_{DATE_STR}'
SSSJ_TABLE = f'monitor_gp_sssj_{DATE_STR}'

# 读取数据
with engine.connect() as conn:
    all_df = pd.read_sql(f"SELECT * FROM {SSSJ_TABLE} WHERE time = '{TIME_STR}'", conn)
    top30_df = pd.read_sql(f"SELECT * FROM {TOP30_TABLE} WHERE time = '{TIME_STR}'", conn)

print(f"股票数据: {len(all_df)} 行, top30: {len(top30_df)} 行")

# 计算行业排行
result = calculate_industry_topn(top30_df, all_df, DATE_STR, TIME_STR)
print(f"行业结果: {len(result)} 行")

if result.empty:
    print("ERROR: 结果为空！")
    sys.exit(1)

# 清理旧表
with engine.connect() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS {HY_TABLE}"))
    conn.commit()
print(f"已删除旧表 {HY_TABLE}")

# 写入MySQL
with engine.connect() as conn:
    result.to_sql(HY_TABLE, con=conn, if_exists='append', index=False)
    conn.commit()
print(f"已写入 {len(result)} 行到 {HY_TABLE}")

# 重建Redis（清除旧key，写入TOP5）
try:
    client = redis_util._get_redis_client()
    code_key = f'rank:industry:code_{DATE_STR}'
    name_key = f'rank:industry:code_name_{DATE_STR}'
    client.delete(code_key)
    client.delete(name_key)
    
    top5 = result.head(5)
    redis_util.update_rank_redis(top5, 'industry', date_str=DATE_STR)
    print(f"已更新Redis排行（TOP5）")
except Exception as e:
    print(f"Redis更新失败: {e}")

# 验证
print(f"\n=== 验证 ===")
with engine.connect() as conn:
    verify = pd.read_sql(f"""
        SELECT code, name, `count`, total, industry_cumulative_main_net, final_score, `rank`
        FROM {HY_TABLE}
        WHERE time = '{TIME_STR}'
        ORDER BY `rank` ASC LIMIT 5
    """, conn)
    print(f"时间点: {TIME_STR}")
    print(f"总行数: {len(result)}")
    print(f"\nTOP5:")
    for _, row in verify.iterrows():
        print(f"  {row['rank']}. {row['name']}: 上涨{row['count']}/{row['total']}, "
              f"主力净额={row['industry_cumulative_main_net']:.0f}, 得分={row['final_score']:.4f}")
    
    # 查表结构
    cols = pd.read_sql(f"SHOW COLUMNS FROM {HY_TABLE}", conn)
    print(f"\n表结构 ({len(cols)} 列):")
    for _, c in cols.iterrows():
        print(f"  {c['Field']} ({c['Type']})")

print(f"\n✅ 完成！前端验证时间点: {TIME_STR}")
print(f"   访问 http://localhost:8080/monitor 查看行业上攻排行")
