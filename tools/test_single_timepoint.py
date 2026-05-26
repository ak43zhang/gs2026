"""测试单个时间点的行业排行数据"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util

db_config = config_util.get_config('mysql', 'url')
if isinstance(db_config, dict):
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    url = db_config
engine = create_engine(url)

time_str = '10:00:00'
print(f"=== 测试时间点: {time_str} ===\n")

# 1. 加载数据
with engine.connect() as conn:
    all_df = pd.read_sql(f"SELECT * FROM monitor_gp_sssj_20260526 WHERE time = '{time_str}'", conn)
    top30_df = pd.read_sql(f"SELECT * FROM monitor_gp_top30_20260526 WHERE time = '{time_str}'", conn)

print(f"all_df: {len(all_df)} rows")
print(f"top30_df: {len(top30_df)} rows")
print(f"cumulative_main_net in all_df: {'cumulative_main_net' in all_df.columns}")

# 2. 检查行业映射
from gs2026.monitor.monitor_stock import get_industry_mapping_cached
mapping = get_industry_mapping_cached()
print(f"industry mapping: {len(mapping)} entries")

# 3. 手动统计行业数量
code_col = 'stock_code' if 'stock_code' in all_df.columns else 'code'
all_df['_ind'] = all_df[code_col].map(lambda x: mapping.get(str(x), {}).get('industry_code', ''))
valid = all_df[all_df['_ind'] != '']
unique_industries = valid['_ind'].nunique()
print(f"unique industries in all_df: {unique_industries}")

# 4. 检查 top30 覆盖了多少行业
top30_code_col = 'stock_code' if 'stock_code' in top30_df.columns else 'code'
top30_df['_ind'] = top30_df[top30_code_col].map(lambda x: mapping.get(str(x), {}).get('industry_code', ''))
top30_industries = top30_df[top30_df['_ind'] != '']['_ind'].nunique()
print(f"unique industries in top30: {top30_industries}")
print(f"top30 stocks: {len(top30_df)}")

# 5. 调用函数
from gs2026.monitor.monitor_stock import calculate_industry_topn
result = calculate_industry_topn(top30_df, all_df, '20260526', time_str)
print(f"\n=== 函数返回结果 ===")
print(f"result rows: {len(result)}")

if not result.empty:
    print(f"columns: {list(result.columns)}")
    # 显示全部
    cols = ['code', 'name', 'count', 'total', 'final_score', 'rank']
    if 'industry_cumulative_main_net' in result.columns:
        cols.insert(4, 'industry_cumulative_main_net')
    print(result[cols].to_string())
else:
    print("结果为空！")

# 6. 分析过滤原因
print(f"\n=== 过滤分析 ===")
# 模拟函数内部逻辑
agg = valid.groupby('_ind').agg({'stock_code': 'count', 'change_pct': 'mean'}).rename(columns={'stock_code': 'total', 'change_pct': 'avg_pct'})

# count > 0 的行业（有top30股票的）
top30_valid = top30_df[top30_df['_ind'] != '']
up_counts = top30_valid.groupby('_ind').size()
agg['count'] = up_counts.reindex(agg.index).fillna(0).astype(int)

total_industries = len(agg)
count_gt_0 = (agg['count'] > 0).sum()
avg_pct_ge_0 = (agg['avg_pct'] >= 0).sum()
both = ((agg['count'] > 0) & (agg['avg_pct'] >= 0)).sum()

print(f"全部行业: {total_industries}")
print(f"count > 0 (有top30股票): {count_gt_0}")
print(f"avg_change_pct >= 0: {avg_pct_ge_0}")
print(f"同时满足两个条件: {both}")
print(f"\n结论: 函数只返回 count>0 且 avg_change_pct>=0 的行业")
print(f"被过滤掉: {total_industries - both} 个行业")
